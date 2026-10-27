"""AI 应用接口（阶段一~三）：创作助手 / 账单解读 / 攻略执行计划。

设计约定：
- 复用 agent/llm.py 的模型调用，不另起一套 HTTP 客户端；
- 提示词集中在 app/agent/prompts.py，本文件只做输入校验、调用和落库；
- 模型输出一律走 json_out.extract_json 解析 + 逐字段清洗，解析失败返回 502 让用户重试，
  绝不把半截文本当结果返回；
- 涉及钱的数字：账单统计由程序算好；实际节省只经 /exec-plans/{id}/confirm-saving
  写入 checkins（唯一省钱口径），AI 的 est_saving 永远不进统计。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.rate_limit import limit_by_user
from app.models.user import User
from app.models.bill import Bill
from app.models.article import Article
from app.models.ai_assist import AICreation, AIBillReport, AIExecPlan
from app.utils.response import success
from app.agent.llm import call_llm_simple, LLMError, friendly_error
from app.agent.json_out import extract_json, AIOutputError, _clean_str, _clean_list_str
from app.agent import prompts

router = APIRouter()

MAX_FIELD = 20000      # 用户输入正文上限，和投稿正文一个量级


def _ask_llm(system: str, user: str) -> dict:
    """统一的「调模型 → 抠 JSON」通道。任何失败都收敛成 502 + 人话。"""
    try:
        raw = call_llm_simple(user, system)
        return extract_json(raw)
    except AIOutputError as e:
        raise HTTPException(502, e.brief)
    except LLMError as e:
        raise HTTPException(502, e.brief)
    except Exception as e:
        raise HTTPException(502, friendly_error(e))


# ==========================================================================
# 阶段一：AI 创作助手
# ==========================================================================

class CreateAssistIn(BaseModel):
    scene: str = "article"              # article / post
    mode: str = "generate"              # generate / title / polish / reorganize
    topic: str = ""                     # 主题
    experience: str = ""                # 经历
    scene_desc: str = ""                # 适用场景
    title: str = ""                     # 润色/重组时的原标题
    content: str = ""                   # 润色/重组/出标题时的原文


def _clean_creation(data: dict, scene: str, cats: list) -> dict:
    """逐字段清洗模型输出。category 不在候选里就落回「综合」，不让脏值进发布表单。"""
    category = _clean_str(data.get("category"), 20)
    if category not in cats:
        category = "综合"
    content = _clean_str(data.get("content"), MAX_FIELD)
    if scene == "post":
        content = _clean_str(data.get("content"), 3000)
    return {
        "title": _clean_str(data.get("title"), 60),
        "summary": _clean_str(data.get("summary"), 100),
        "content": content,
        "category": category,
        "tags": _clean_list_str(data.get("tags"), 4, 20),
        "steps": _clean_list_str(data.get("steps"), 10, 200),
        "notes": _clean_list_str(data.get("notes"), 8, 200),
    }


@router.post("/create-assist")
def create_assist(
    req: CreateAssistIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(limit_by_user("ai_create")),
):
    scene = req.scene if req.scene in ("article", "post") else "article"
    mode = req.mode if req.mode in ("generate", "title", "polish", "reorganize") else "generate"
    cats = ["餐饮", "购物", "生活", "羊毛", "交通", "综合"]

    content = (req.content or "").strip()
    if mode in ("polish", "reorganize") and len(content) < 10:
        raise HTTPException(400, "先写点内容再让 AI 润色或重组")
    if mode == "generate" and len((req.topic or "").strip()) < 2:
        raise HTTPException(400, "填一下主题，比如「食堂一日三餐怎么吃省」")

    kind = "社区经验帖" if scene == "post" else "省钱攻略"
    tpl = prompts.CREATE_ASSIST_USER[mode]
    # 输出格式说明里有 JSON 花括号，不能进 str.format，在格式化之后拼上去
    filled = tpl.format(
        cats=prompts.ARTICLE_CATS,
        topic=_clean_str(req.topic, 200),
        experience=_clean_str(req.experience, 2000)[:2000],
        scene_desc=_clean_str(req.scene_desc, 500),
        title=_clean_str(req.title, 100),
        content=content[:MAX_FIELD],
        content_head=content[:300],
        kind=kind,
    ) + prompts._CREATE_SHAPE
    if scene == "post":
        filled += "\n" + prompts.POST_NOTE

    data = _ask_llm(prompts.CREATE_ASSIST_SYSTEM, filled)
    result = _clean_creation(data, scene, cats)
    if mode in ("generate", "polish", "reorganize") and len(result["content"]) < 10:
        # 正文是这三种模式的硬产出，太短说明模型跑题了
        raise HTTPException(502, "AI 返回的正文太短，请重试一次")

    row = AICreation(
        user_id=current_user.id, scene=scene, mode=mode,
        input_json=json.dumps({
            "topic": req.topic or "", "experience": (req.experience or "")[:500],
            "scene_desc": req.scene_desc or "", "title": req.title or "",
            "content_head": content[:300],
        }, ensure_ascii=False),
        output_json=json.dumps(result, ensure_ascii=False),
        model=_model_name(),
    )
    db.add(row)
    db.commit()
    return success({"id": row.id, "result": result}, "已生成，请检查修改后再发布")


def _model_name() -> str:
    from app.core.config import LLM_MODEL
    return LLM_MODEL


@router.get("/creations")
def my_creations(
    scene: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 创作历史：最近 20 条，前端可回填草稿继续改。"""
    query = db.query(AICreation).filter(AICreation.user_id == current_user.id)
    if scene in ("article", "post"):
        query = query.filter(AICreation.scene == scene)
    rows = query.order_by(AICreation.id.desc()).limit(20).all()
    items = []
    for r in rows:
        try:
            out = json.loads(r.output_json or "{}")
        except json.JSONDecodeError:
            out = {}
        items.append({
            "id": r.id, "scene": r.scene, "mode": r.mode,
            "title": out.get("title") or "(无标题)",
            "summary": out.get("summary") or "",
            "result": out,
            "article_id": r.article_id or 0,
            "created_at": str(r.created_at)[:16] if r.created_at else "",
        })
    return success({"items": items})


# ==========================================================================
# 阶段二：AI 账单解读（统计程序算，AI 只解读）
# ==========================================================================

def _bill_stats(db: Session, user_id: int, month: str) -> dict:
    """月度账单统计快照。确定性计算全部在这里，AI 只读这份结果。

    形状与 /bills/analysis 保持同一口径（分类/环比），但独立成函数，
    供报告生成和落库快照共用。
    """
    from datetime import datetime
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        month = datetime.now().strftime("%Y-%m")
        y, m = int(month[:4]), int(month[5:7])
    prev_str = "%04d-%02d" % ((y - 1, 12) if m == 1 else (y, m - 1))

    rows = (db.query(Bill.category, func.sum(Bill.amount), func.count(Bill.id))
            .filter(Bill.user_id == user_id,
                    func.date_format(Bill.bill_date, "%Y-%m") == month)
            .group_by(Bill.category).all())
    total = sum(float(r[1] or 0) for r in rows)
    cnt = sum(r[2] for r in rows)
    categories = [{
        "name": r[0] or "其他",
        "amount": round(float(r[1] or 0), 2),
        "pct": round(float(r[1] or 0) / total * 100, 1) if total > 0 else 0,
        "count": r[2],
    } for r in rows]
    categories.sort(key=lambda x: x["amount"], reverse=True)

    prev_total = float(db.query(func.coalesce(func.sum(Bill.amount), 0))
                       .filter(Bill.user_id == user_id,
                               func.date_format(Bill.bill_date, "%Y-%m") == prev_str)
                       .scalar() or 0)
    days = (db.query(func.count(func.distinct(func.date(Bill.bill_date))))
            .filter(Bill.user_id == user_id,
                    func.date_format(Bill.bill_date, "%Y-%m") == month).scalar()) or 0

    return {
        "month": month,
        "total": round(total, 2),
        "count": cnt,
        "days_with_bills": days,
        "daily_avg": round(total / days, 2) if days > 0 else 0,
        "categories": categories,
        "prev_month": prev_str,
        "prev_total": round(prev_total, 2),
        "diff": round(total - prev_total, 2),
        "diff_pct": round((total - prev_total) / prev_total * 100, 1) if prev_total > 0 else None,
    }


class BillReportIn(BaseModel):
    month: str = ""                     # YYYY-MM，空=当月


@router.post("/bill-report")
def create_bill_report(
    req: BillReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(limit_by_user("ai_bill_report")),
):
    from datetime import datetime
    month = (req.month or "").strip() or datetime.now().strftime("%Y-%m")
    stats = _bill_stats(db, current_user.id, month)

    if stats["count"] == 0:
        # 没数据就不烧 token，也不让 AI 编一份「分析」出来
        return success({
            "month": month, "report": None, "stats": stats,
            "empty": True, "message": "%s 还没有账单记录，先记几笔再来看解读" % month,
        })

    # 数据不完整的两种情形：笔数太少 / 只有单一分类。如实告知 AI，让它下结论前先声明
    data_note = ""
    if stats["count"] < 5 or len(stats["categories"]) < 2:
        data_note = ("（注意：这个月只有 %d 笔账单、%d 个分类，数据不完整，"
                     "解读时必须先说明数据有限，不下确定性结论）"
                     % (stats["count"], len(stats["categories"])))

    filled = prompts.BILL_REPORT_USER.format(
        month=month, stats_json=json.dumps(stats, ensure_ascii=False),
        data_note=data_note,
    )
    data = _ask_llm(prompts.BILL_REPORT_SYSTEM, filled)

    # glm-4-flash 偶尔把 summary 写成 {"分类": "xx元 (xx%)"} 的 JSON 串，
    # 实测出现过。转成「分类 xx元（xx%）；…」的短句，数字原样保留、不重算。
    summary = _clean_str(data.get("summary"), 500)
    if summary.startswith("{"):
        try:
            m = json.loads(summary)
            if isinstance(m, dict):
                summary = "；".join("%s %s" % (k, v) for k, v in list(m.items())[:8])
        except json.JSONDecodeError:
            pass

    report = {
        "summary": summary,
        "points": [],
        "advice": _clean_str(data.get("advice"), 300),
        "data_limited": bool(data.get("data_limited")) or bool(data_note),
    }
    for p in (data.get("points") or [])[:4]:
        if isinstance(p, dict):
            t, x = _clean_str(p.get("title"), 40), _clean_str(p.get("text"), 300)
            if t or x:
                report["points"].append({"title": t or "分析", "text": x})
        elif isinstance(p, str) and p.strip():
            report["points"].append({"title": "分析", "text": p.strip()[:300]})
    if not report["summary"] and not report["points"]:
        raise HTTPException(502, "AI 没有给出有效解读，请重试一次")

    row = AIBillReport(
        user_id=current_user.id, month=month,
        stats_json=json.dumps(stats, ensure_ascii=False),
        report_json=json.dumps(report, ensure_ascii=False),
        model=_model_name(),
    )
    db.add(row)
    db.commit()
    return success({"month": month, "report": report, "stats": stats,
                    "empty": False, "id": row.id}, "解读已生成")


@router.get("/bill-reports")
def list_bill_reports(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """历史解读报告：只回列表元信息，正文按 id 取。"""
    from datetime import datetime
    query = db.query(AIBillReport).filter(AIBillReport.user_id == current_user.id)
    if (month or "").strip():
        query = query.filter(AIBillReport.month == month.strip())
    rows = query.order_by(AIBillReport.id.desc()).limit(20).all()
    return success({"items": [{
        "id": r.id, "month": r.month,
        "summary": _clean_str((json.loads(r.report_json or "{}")).get("summary"), 80),
        "created_at": str(r.created_at)[:16] if r.created_at else "",
    } for r in rows]})


@router.get("/bill-reports/{report_id}")
def get_bill_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(AIBillReport).filter(
        AIBillReport.id == report_id, AIBillReport.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "报告不存在")
    try:
        report = json.loads(row.report_json or "{}")
        stats = json.loads(row.stats_json or "{}")
    except json.JSONDecodeError:
        raise HTTPException(500, "历史报告数据损坏")
    return success({"id": row.id, "month": row.month,
                    "report": report, "stats": stats,
                    "created_at": str(row.created_at)[:16] if row.created_at else ""})


# ==========================================================================
# 阶段三：AI 攻略拆解与执行计划
# ==========================================================================

class ExecPlanIn(BaseModel):
    article_id: int


def _plan_json(row: AIExecPlan) -> dict:
    try:
        return json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        return {}


def _plan_payload(row: AIExecPlan, article_title: str = "") -> dict:
    plan = _plan_json(row)
    return {
        "id": row.id, "article_id": row.article_id,
        "article_title": article_title or row.title,
        "title": row.title,
        "plan": plan,
        "est_saving": round(float(row.est_saving or 0), 2),
        "actual_saving": round(float(row.actual_saving or 0), 2),
        "status": row.status or "进行中",
        "created_at": str(row.created_at)[:16] if row.created_at else "",
    }


@router.post("/exec-plan")
def create_exec_plan(
    req: ExecPlanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(limit_by_user("ai_exec_plan")),
):
    a = db.query(Article).filter(Article.id == req.article_id).first()
    if not a:
        raise HTTPException(404, "攻略不存在")
    if len((a.content or "")) < 10:
        raise HTTPException(400, "这篇攻略正文太短，拆不出执行计划")

    filled = prompts.EXEC_PLAN_USER.format(
        title=a.title, content=a.content[:MAX_FIELD])
    data = _ask_llm(prompts.EXEC_PLAN_SYSTEM, filled)

    steps = []
    for s in (data.get("steps") or [])[:10]:
        if isinstance(s, dict):
            text = _clean_str(s.get("text"), 200)
            if text:
                steps.append({"text": text, "note": _clean_str(s.get("note"), 200),
                              "done": False})
        elif isinstance(s, str) and s.strip():
            steps.append({"text": s.strip()[:200], "note": "", "done": False})
    if not steps:
        raise HTTPException(502, "AI 没拆出执行步骤，请重试一次")

    shopping = []
    for s in (data.get("shopping") or [])[:6]:
        if not isinstance(s, dict):
            continue
        name = _clean_str(s.get("name"), 60)
        if not name:
            continue
        try:
            est = round(float(s.get("est_price") or 0), 2)
        except (TypeError, ValueError):
            est = 0
        shopping.append({"name": name, "est_price": max(0.0, est),
                         "spec": _clean_str(s.get("spec"), 100),
                         "actual": 0, "bought": False})
    est_saving = 0.0
    try:
        est_saving = max(0.0, round(float(data.get("est_saving") or 0), 2))
    except (TypeError, ValueError):
        pass

    plan = {
        "steps": steps,
        "shopping": shopping,
        "prep": _clean_list_str(data.get("prep"), 8, 200),
        "cautions": _clean_list_str(data.get("cautions"), 8, 200),
        "budget_advice": _clean_str(data.get("budget_advice"), 300),
        "product_keywords": _clean_list_str(data.get("product_keywords"), 3, 40),
    }
    row = AIExecPlan(
        user_id=current_user.id, article_id=a.id, title=a.title[:200],
        plan_json=json.dumps(plan, ensure_ascii=False),
        est_saving=est_saving, model=_model_name(),
    )
    db.add(row)
    db.commit()
    return success(_plan_payload(row), "执行计划已生成，可勾选进度和记录实际花费")


@router.get("/exec-plans")
def my_exec_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (db.query(AIExecPlan).filter(AIExecPlan.user_id == current_user.id)
            .order_by(AIExecPlan.id.desc()).limit(50).all())
    items = []
    for r in rows:
        plan = _plan_json(r)
        steps = plan.get("steps") or []
        done = sum(1 for s in steps if s.get("done"))
        items.append({
            "id": r.id, "title": r.title, "article_id": r.article_id,
            "status": r.status or "进行中",
            "steps_done": done, "steps_total": len(steps),
            "est_saving": round(float(r.est_saving or 0), 2),
            "actual_saving": round(float(r.actual_saving or 0), 2),
            "created_at": str(r.created_at)[:16] if r.created_at else "",
        })
    return success({"items": items})


@router.get("/exec-plans/{plan_id}")
def get_exec_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(AIExecPlan).filter(
        AIExecPlan.id == plan_id, AIExecPlan.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "计划不存在")
    return success(_plan_payload(row))


class ExecPlanUpdate(BaseModel):
    steps: list = None                  # [{text, note, done}] 整包替换（前端编辑后提交）
    shopping: list = None               # [{name, est_price, spec, actual, bought}]
    status: str = ""                    # 进行中 / 已完成


@router.put("/exec-plans/{plan_id}")
def update_exec_plan(
    plan_id: int,
    req: ExecPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存用户对计划的编辑：勾选步骤、填实买金额、改状态。

    只接受这些白名单字段；actual_saving 不在这里改——走 confirm-saving，
    那里才有钱进 checkins 的唯一通道。
    """
    row = db.query(AIExecPlan).filter(
        AIExecPlan.id == plan_id, AIExecPlan.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "计划不存在")
    plan = _plan_json(row)

    if req.steps is not None:
        steps = []
        for s in req.steps[:10]:
            if not isinstance(s, dict):
                continue
            text = _clean_str(s.get("text"), 200)
            if not text:
                continue
            steps.append({"text": text, "note": _clean_str(s.get("note"), 200),
                          "done": bool(s.get("done"))})
        if steps:
            plan["steps"] = steps

    if req.shopping is not None:
        shopping = []
        for s in req.shopping[:6]:
            if not isinstance(s, dict):
                continue
            name = _clean_str(s.get("name"), 60)
            if not name:
                continue
            try:
                est = max(0.0, round(float(s.get("est_price") or 0), 2))
                act = max(0.0, round(float(s.get("actual") or 0), 2))
            except (TypeError, ValueError):
                est, act = 0.0, 0.0
            shopping.append({"name": name, "est_price": est,
                             "spec": _clean_str(s.get("spec"), 100),
                             "actual": act, "bought": bool(s.get("bought"))})
        plan["shopping"] = shopping

    row.plan_json = json.dumps(plan, ensure_ascii=False)
    if req.status in ("进行中", "已完成"):
        row.status = req.status
    from datetime import datetime
    row.updated_at = datetime.now()
    db.commit()
    return success({"id": row.id, "status": row.status}, "已保存")


class ConfirmSavingIn(BaseModel):
    amount: float
    note: str = ""


@router.post("/exec-plans/{plan_id}/confirm-saving")
def confirm_plan_saving(
    plan_id: int,
    req: ConfirmSavingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把用户确认的实际节省记入省钱成果（checkins 表，source=攻略）。

    est_saving 是 AI 预测，永远不进统计；这里只收用户手动确认的金额，
    校验、重算月累计和 total_saved 全部复用打卡接口的同一套逻辑。
    """
    from datetime import date as _date
    from app.models.checkin import Checkin
    from app.models.budget_plan import BudgetPlan
    from app.api.routes.checkin import _recompute_month

    if not (0 < req.amount < 10 ** 8):
        raise HTTPException(400, "金额要大于 0 且不能离谱")

    row = db.query(AIExecPlan).filter(
        AIExecPlan.id == plan_id, AIExecPlan.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "计划不存在")

    today = _date.today()
    month = today.strftime("%Y-%m")
    amount = round(float(req.amount), 2)

    # 幂等：同一用户、同一攻略、同一天、同一金额的确认只入账一次。
    # 双击按钮或网络重试不该造出两笔「实际省钱」
    dup_q = db.query(Checkin).filter(
        Checkin.user_id == current_user.id,
        Checkin.source == "攻略",
        Checkin.ref_type == "article",
        Checkin.day == today,
        Checkin.saved_amount == amount,
    )
    dup_q = dup_q.filter(Checkin.ref_id == row.article_id) if row.article_id \
        else dup_q.filter(Checkin.ref_id.is_(None))
    if dup_q.first():
        return success({"duplicate": True, "actual_saving": row.actual_saving,
                        "checkin_month_total": None},
                       "这笔省钱刚确认过了，没有重复入账")

    plan_row = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id, BudgetPlan.month == month).first()
    if not plan_row:
        plan_row = BudgetPlan(user_id=current_user.id, month=month, target_amount=500)
        db.add(plan_row)
        db.commit()
        db.refresh(plan_row)

    before_total = float(plan_row.saved_amount or 0)
    db.add(Checkin(user_id=current_user.id, day=today,
                   saved_amount=amount,
                   note=("照攻略《%s》执行：%s" % (row.title, req.note or "")).strip()[:120],
                   source="攻略", ref_type="article", ref_id=row.article_id or None))
    db.commit()
    _recompute_month(db, current_user, plan_row, month, before_total)
    db.commit()

    row.actual_saving = amount
    row.status = "已完成"
    from datetime import datetime
    row.updated_at = datetime.now()
    db.commit()
    return success({"duplicate": False, "actual_saving": row.actual_saving,
                    "checkin_month_total": plan_row.saved_amount},
                   "已确认记入省钱成果")
