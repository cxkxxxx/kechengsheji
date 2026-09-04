

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False)            # 标题
    content = Column(Text, nullable=False)                 # 正文（Markdown）
    category = Column(String(50), default="综合")          # 分类：餐饮/购物/生活/羊毛
    cover = Column(String(500))                            # 封面图 URL
    author = Column(String(50), default="抠门达人")        # 作者
    likes = Column(Integer, default=0)                     # 点赞数
    views = Column(Integer, default=0)                     # 浏览量
    created_at = Column(DateTime, server_default=func.now())
