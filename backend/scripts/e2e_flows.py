# -*- coding: utf-8 -*-
"""联调阶段端到端验证：A/B/C/D 四条业务流，真实 MySQL + 真实 glm-4-flash。

A  AI创作 → 编辑 → 提交审核（带 creation_id）→ 管理员通过 → 发布结果可见 + 草稿回填
B  账单 → AI 分析 → 保存报告 → 历史查看
C  攻略 → 执行计划 → 保存勾选/实买 → 确认节省（幂等）→ 账单记录/个人统计
D  管理员 AI 审查 → 查看理由 → 人工通过

跑法：PYTHONIOENCODING=utf-8 python scripts/e2e_flows.py
测试账号与数据留在 dev 库，不影响真实用户。
"""
import sys
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.ai_assist import AICreation
from app.models.checkin import Checkin

c = TestClient(app)
U = "ai_e2e_20261026"
P = "e2e123456"
FAILS = []


def ok(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + (" | " + str(detail) if detail else ""))
    if not cond:
        FAILS.append(name)


def j(r):
    d = r.json()
    assert r.status_code < 500, (r.status_code, d)
    return d


# ---------- 登录 ----------
c.post("/auth/register", json={"nickname": U, "password": P})
r = c.post("/auth/login-password", json={"nickname": U, "password": P})
tok = j(r)["data"]["token"]
H = {"Authorization": "Bearer " + tok}
uid = j(c.get("/auth/me", headers=H))["data"]["id"] if True else 0
print("user id:", uid)

# ============================================================
print("\n== A. AI创作 → 提交审核 → 管理员通过 → 发布结果 ==")
r = c.post("/ai/create-assist", json={
    "scene": "article", "mode": "generate",
    "topic": "超市晚间打折菜怎么挑",
    "experience": "晚上8点后熟食和面包区常打折，我固定那个点去，一周省20左右",
}, headers=H)
d = j(r)
cre_id = (d.get("data") or {}).get("id")
res = (d.get("data") or {}).get("result") or {}
ok("A1 create-assist 返回 creation id", bool(cre_id), cre_id)
ok("A2 AI 草稿有标题和正文", bool(res.get("title")) and len(res.get("content") or "") >= 10,
   (res.get("title") or "")[:30])

draft = dict(res)
draft["content"] = (draft.get("content") or "") + "\n\n（我自己补充：打折区东西要当天吃完）"
r = c.post("/articles", headers=H, json={
    "title": draft.get("title") or "超市晚间打折攻略",
    "content": draft["content"], "category": draft.get("category") or "购物",
    "creation_id": cre_id})
d = j(r)
art_id = (d.get("data") or {}).get("id")
ok("A3 投稿成功 pending", d["code"] == 200 and (d["data"].get("status") == "pending"), d.get("message"))

db = SessionLocal()
cre = db.query(AICreation).get(cre_id)
ok("A4 ai_creations.article_id 已回填", cre.article_id == art_id,
   "creation.article_id=%s article=%s" % (cre.article_id, art_id))
db.close()

r = c.get("/articles/%s" % art_id)
ok("A5 未过审时详情不可见", (r.json().get("data") in (None, {})), r.json().get("message"))

c.post("/admin/api/login", json={"username": "admin", "password": "admin123"})
atok = j(c.post("/admin/api/login", json={"username": "admin", "password": "admin123"}))["data"]["token"]
AH = {"Authorization": "Bearer " + atok}
r = c.put("/admin/api/articles/%s" % art_id, headers=AH,
          json={"title": draft.get("title"), "content": draft["content"],
                "category": draft.get("category") or "购物", "status": "approved"})
ok("A6 管理员人工通过", j(r)["code"] == 200, r.json().get("message"))
r = c.get("/articles/%s" % art_id)
ok("A7 通过后详情可见", (r.json().get("data") or {}).get("id") == art_id)
r = c.get("/ai/creations?scene=article", headers=H)
it = [x for x in j(r)["data"]["items"] if x["id"] == cre_id]
ok("A8 历史里标记为已发布", it and it[0]["article_id"] == art_id, it and it[0]["article_id"])

# ============================================================
print("\n== B. 账单 → AI 分析 → 报告 → 历史 ==")
c.post("/bills/seed-demo?month=2026-10&months=2", headers=H)
r = c.post("/ai/bill-report", json={"month": "2026-10"}, headers=H)
d = j(r)
rep = (d.get("data") or {}).get("report") or {}
rid = (d.get("data") or {}).get("id")
ok("B1 报告生成并落库", d["code"] == 200 and bool(rid) and bool(rep.get("summary")),
   "id=%s" % rid)
ok("B2 AI 未编造数字口径", (d["data"].get("stats") or {}).get("total") is not None,
   (d["data"].get("stats") or {}).get("total"))
r = c.get("/ai/bill-reports?month=2026-10", headers=H)
ok("B3 历史列表含这份报告", any(x["id"] == rid for x in j(r)["data"]["items"]))
r = c.get("/ai/bill-reports/%s" % rid, headers=H)
ok("B4 按 id 回看报告", j(r)["code"] == 200 and (j(r)["data"].get("report") or {}).get("summary"))

# ============================================================
print("\n== C. 执行计划 → 勾选/实买 → 确认节省（幂等）→ 账单 ==")
r = c.get("/checkin/records?month=2026-10", headers=H)
before = j(r)["data"]["records"]
before_cnt = len([x for x in before if x["source"] == "攻略"])
r = c.post("/ai/exec-plan", json={"article_id": art_id}, headers=H)
d = j(r)
payload = d.get("data") or {}
plan = payload.get("plan") or {}
pid = payload.get("id")
ok("C1 执行计划生成", d["code"] == 200 and bool(pid) and len(plan.get("steps") or []) > 0,
   "steps=%s shopping=%s est=%s" % (len(plan.get("steps") or []),
                                    len(plan.get("shopping") or []), payload.get("est_saving")))
steps = plan.get("steps") or []
steps[0]["done"] = True
shop = plan.get("shopping") or []
if shop:
    shop[0]["actual"] = 12.8
    shop[0]["bought"] = True
r = c.put("/ai/exec-plans/%s" % pid, headers=H, json={"steps": steps, "shopping": shop})
ok("C2 计划保存", j(r)["code"] == 200)
r = c.get("/ai/exec-plans/%s" % pid, headers=H)
det = j(r)["data"]
ok("C3 勾选和实买金额已持久化", (det["plan"]["steps"][0].get("done") is True)
   and (det["plan"]["shopping"][0].get("actual") == 12.8 if det["plan"]["shopping"] else False))

amt = 23.5
r1 = c.post("/ai/exec-plans/%s/confirm-saving" % pid, headers=H, json={"amount": amt, "note": "e2e"})
d1 = j(r1)
r2 = c.post("/ai/exec-plans/%s/confirm-saving" % pid, headers=H, json={"amount": amt, "note": "e2e"})
d2 = j(r2)
ok("C4 第一次确认入账", d1["code"] == 200 and d1["data"]["duplicate"] is False, d1.get("message"))
ok("C5 重复请求被幂等挡住", d2["code"] == 200 and d2["data"]["duplicate"] is True, d2.get("message"))
db = SessionLocal()
n = db.query(Checkin).filter(Checkin.user_id == uid, Checkin.source == "攻略",
                             Checkin.ref_id == art_id).count()
db.close()
ok("C6 checkins 只有一笔", n == 1, "count=%s" % n)
r = c.get("/checkin/records?month=2026-10", headers=H)
after = [x for x in j(r)["data"]["records"] if x["source"] == "攻略"]
ok("C7 省钱记录列表可见且带关联标题", len(after) == before_cnt + 1
   and all(x.get("ref_title") for x in after[:1]), after[:1])
r = c.get("/ai/exec-plans/%s" % pid, headers=H)
ok("C8 计划状态=已完成 且 actual_saving 镜像", j(r)["data"]["status"] == "已完成"
   and j(r)["data"].get("actual_saving") == amt)
r = c.get("/auth/me", headers=H)
ok("C9 个人累计 total_saved 增长", float((j(r)["data"] or {}).get("total_saved") or 0) >= amt,
   (j(r)["data"] or {}).get("total_saved"))

# ============================================================
print("\n== D. 管理员 AI 审查 → 理由 → 人工决定 ==")
r = c.post("/articles", headers=H, json={
    "title": "e2e 审查投稿：转发这条链接免费领百元话费",
    "content": "点击链接填写手机号就能免费领100元话费，亲测有效，快来转发给同学！"})
bad_id = j(r)["data"]["id"]
r = c.post("/admin/api/ai-review", headers=AH, json={"target_type": "article", "target_id": bad_id})
d = j(r)
res = (d.get("data") or {}).get("result") or {}
ok("D1 AI 审查给出风险标签与理由", bool(res.get("risk_tags") or res.get("spam"))
   and bool(res.get("reason")), res.get("risk_tags"))
ok("D2 需要人工复核标记存在", "needs_human" in res, res.get("needs_human"))
r = c.get("/admin/api/ai-review?target_type=article&target_id=%s" % bad_id, headers=AH)
ok("D3 审查记录可回看（不重复烧模型）", j(r)["code"] == 200
   and bool((j(r)["data"] or {}).get("result") or (j(r)["data"] or {}).get("result_json")))
r = c.put("/admin/api/articles/%s" % bad_id, headers=AH,
          json={"title": "e2e 审查投稿：转发这条链接免费领百元话费",
                "content": "点击链接填写手机号就能免费领100元话费，亲测有效，快来转发给同学！",
                "category": "羊毛", "status": "rejected"})
ok("D4 管理员最终人工驳回", j(r)["code"] == 200)
r = c.get("/articles/%s" % bad_id)
ok("D5 驳回后公开列表不可见", r.json().get("data") in (None, {}))

print("\n" + "=" * 50)
if FAILS:
    print("E2E FAILED: %d 项 -> %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("E2E ALL PASS (A/B/C/D)")
