# 收藏表
# ==============================
# 用户收藏的攻略文章或帖子
""
from sqlalchemy import Column, Integer, String, DateTime, func
from app.core.database import Base

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    target_type = Column(String(20), nullable=False)       # "article" 或 "post"
    target_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
