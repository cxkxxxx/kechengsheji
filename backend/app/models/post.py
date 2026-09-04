

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)              # 发帖人 ID
    title = Column(String(200), nullable=False)            # 标题
    content = Column(Text, nullable=False)                 # 正文
    images = Column(Text)                                  # 图片 URL 列表（JSON 字符串）
    tags = Column(String(200))                             # 标签（逗号分隔）
    status = Column(String(20), default="approved")        # 状态：pending/approved/rejected
    likes = Column(Integer, default=0)                     # 点赞数
    comments_count = Column(Integer, default=0)            # 评论数
    created_at = Column(DateTime, server_default=func.now())
