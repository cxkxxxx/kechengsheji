# 管理端账号模型
from sqlalchemy import Column, Integer, String, DateTime, func
from app.core.database import Base

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)  # 账号
    password_hash = Column(String(128), nullable=False)                     # 密码哈希
    created_at = Column(DateTime, server_default=func.now())