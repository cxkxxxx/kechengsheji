

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)              # 评论者 ID
    target_type = Column(String(20), nullable=False)       # "article" 或 "post"
    target_id = Column(Integer, nullable=False)            # 文章或帖子 ID
    content = Column(Text, nullable=False)                 # 评论内容
    parent_id = Column(Integer, default=0)                 # 父评论 ID（0=一级评论）
    created_at = Column(DateTime, server_default=func.now())
