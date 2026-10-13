import json

from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.agent.roles import DEFAULT_AGENT, normalize
from app.models.chat_record import ChatRecord

MAX_HISTORY_ROUNDS = 20
# 单条历史与整段历史的字符上限。实测一条 5000 字的分享文案 ≈ 2500 token，
# 而它会在后面 20 轮里每轮重发一遍，带工具的那轮还要算两次；截断后最多多花一点点。
# 只截「历史」，用户本轮刚发的消息不走这里，所以不影响他这次的提问。
MAX_RECORD_CHARS = 400
MAX_HISTORY_CHARS = 3000

# 抠门达人下线后，它那批 agent='default'（以及加列之前的 NULL）记录归到优惠情报员，
# 否则用户原来的对话会凭空消失
LEGACY_AGENTS = ("default", DEFAULT_AGENT)


def _by_agent(query, agent: str):
    name = normalize(agent)
    if name == DEFAULT_AGENT:
        return query.filter(or_(ChatRecord.agent.is_(None), ChatRecord.agent.in_(LEGACY_AGENTS)))
    return query.filter(ChatRecord.agent == name)


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _fit(records: list) -> list:
    """把「新→旧」的记录收成预算内的历史，返回时间正序。

    单独拆出来是为了能不带数据库也验证这段预算逻辑。
    """
    kept, used = [], 0
    for r in records:
        text = _clip(r.content, MAX_RECORD_CHARS)
        # kept 为空时必须收下最新一条，否则一轮都留不下
        if kept and used + len(text) > MAX_HISTORY_CHARS:
            break
        used += len(text)
        kept.append({"role": r.role, "content": text})
    kept.reverse()
    return kept


def get_history(user_id: int, db: Session, agent: str = DEFAULT_AGENT) -> list:
    # 只取同一个智能体的历史：否则在「优惠情报员」里聊过的内容会串进「理财管家」的人设
    query = (db.query(ChatRecord)
             .filter(ChatRecord.user_id == user_id)
             .filter(ChatRecord.role.in_(["user", "assistant"]))
             # 失败时那句「暂时无法响应」不是真回答，读回去模型会以为自己也这么说过；
             # 用户行 tool_calls 是 NULL，直接 != 会被 SQL 判成 NULL 而把整段历史滤空
             .filter(or_(ChatRecord.tool_calls.is_(None), ChatRecord.tool_calls != "error")))
    query = _by_agent(query, agent)
    # 排序是新→旧，正好是 _fit 要的收法（从最新往回收才好在预算处截断）
    return _fit(query.order_by(ChatRecord.created_at.desc(), ChatRecord.id.desc())
                .limit(MAX_HISTORY_ROUNDS * 2).all())


def list_history(user_id: int, db: Session, agent: str = DEFAULT_AGENT, limit: int = 40) -> list:
    # 给前端回显对话气泡用（按时间正序）
    query = (db.query(ChatRecord)
             .filter(ChatRecord.user_id == user_id)
             .filter(ChatRecord.role.in_(["user", "assistant"]))
             .filter(ChatRecord.content.isnot(None)))
    query = _by_agent(query, agent)
    rows = query.order_by(ChatRecord.created_at.desc(), ChatRecord.id.desc()).limit(limit).all()
    rows.reverse()
    out = []
    for r in rows:
        out.append({"id": r.id, "role": r.role, "content": r.content or "",
                    "tool_used": r.tool_calls or "",
                    "links": _json_list(r.links), "tables": _json_list(r.tables),
                    "created_at": str(r.created_at)})
    return out


def _json_list(raw: str) -> list:
    """links / tables 存的是 JSON 数组字符串，坏数据回退成空列表而不是让接口 500。"""
    if not raw:
        return []
    try:
        got = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return got if isinstance(got, list) else []


def clear_history(user_id: int, db: Session, agent: str = DEFAULT_AGENT) -> int:
    return _by_agent(db.query(ChatRecord).filter(ChatRecord.user_id == user_id), agent) \
        .delete(synchronize_session=False)
