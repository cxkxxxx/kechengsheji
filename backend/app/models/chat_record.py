

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class ChatRecord(Base):
    __tablename__ = "chat_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)              # 用户 ID
    role = Column(String(20), nullable=False)              # "user" / "assistant" / "tool"
    content = Column(Text)                                 # 消息内容
    tool_calls = Column(Text)                              # Agent 调用的工具信息（JSON）
    tokens_used = Column(Integer, default=0)               # 消耗 token 数
    created_at = Column(DateTime, server_default=func.now())
