# 用户表模型
# ==============================
# 存储微信小程序用户的基本信息和省钱目标
""
from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # 主键
    openid = Column(String(64), unique=True, index=True)   # 微信 openid
    nickname = Column(String(50))                          # 昵称
    avatar = Column(String(500))                           # 头像 URL
    password_hash = Column(String(120))                    # 昵称密码登录用；纯微信登录的用户为 NULL
    budget_goal = Column(Float, default=0)                 # 月度省钱目标（元）
    total_saved = Column(Float, default=0)                 # 累计已省金额
    # 账号状态：active 正常 / disabled 停用 / deleted 软删除。
    # 管理端「删除」走软删除，保留帖子/账单等业务关联，不做级联物理删除。
    status = Column(String(20), default="active", server_default="active")
    created_at = Column(DateTime, server_default=func.now())  # 注册时间
