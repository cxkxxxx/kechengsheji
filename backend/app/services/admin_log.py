"""管理端写操作留痕。只记一句话说明，不存请求体里的敏感正文。"""
from app.models.admin_log import AdminLog


def record(db, admin, action: str, target_type: str = "", target_id: int = 0, detail: str = ""):
    try:
        db.add(AdminLog(
            admin_id=getattr(admin, "id", 0) or 0,
            admin_name=getattr(admin, "username", "") or "",
            action=action[:40],
            target_type=(target_type or "")[:30],
            target_id=int(target_id or 0),
            detail=(detail or "")[:300],
        ))
        db.commit()
    except Exception:
        db.rollback()   # 留痕失败不该把主业务一起拖垮
