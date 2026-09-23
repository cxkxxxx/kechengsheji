"""帖子点赞记录模型"""
from sqlalchemy import Column, Integer, DateTime, UniqueConstraint, func
from app.core.database import Base


class PostLike(Base):
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    post_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_user_post"),)
