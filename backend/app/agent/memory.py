from sqlalchemy.orm import Session
from app.models.chat_record import ChatRecord

MAX_HISTORY_ROUNDS = 20


def get_history(user_id: int, db: Session) -> list:
    records = (
        db.query(ChatRecord)
        .filter(ChatRecord.user_id == user_id)
        .filter(ChatRecord.role.in_(["user", "assistant"]))
        .order_by(ChatRecord.created_at.desc())
        .limit(MAX_HISTORY_ROUNDS * 2)
        .all()
    )
    records.reverse()
    return [{"role": r.role, "content": r.content or ""} for r in records]
