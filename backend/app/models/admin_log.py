"""管理端操作日志：谁在什么时候对哪条数据做了什么。

毕业设计答辩要能追溯管理操作；也是「重要操作留痕」的安全要求。
只记管理端的写操作，不记用户端行为，也不存请求体里的敏感正文。
"""
from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, nullable=False, index=True)
    admin_name = Column(String(50), default="")
    action = Column(String(40), nullable=False)        # create/update/delete/status/login...
    target_type = Column(String(30), default="")       # user/article/post/comment/price/coupon/admin/ai_review
    target_id = Column(Integer, default=0)
    detail = Column(String(300), default="")           # 一句话说明，不含敏感正文
    created_at = Column(DateTime, server_default=func.now())
