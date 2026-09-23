
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.favorite import Favorite
from app.utils.response import success

router = APIRouter()

@router.post("/toggle")
def toggle_favorite(
    target_type: str,
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 切换收藏状态（已收藏则取消，未收藏则添加）
    fav = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.target_type == target_type,
        Favorite.target_id == target_id,
    ).first()
    if fav:
        db.delete(fav)
        db.commit()
        return success({"favorited": False})
    fav = Favorite(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(fav)
    db.commit()
    return success({"favorited": True})

@router.get("/list")
def my_favorites(
    target_type: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 获取我的收藏列表
    query = db.query(Favorite).filter(Favorite.user_id == current_user.id)
    if target_type:
        query = query.filter(Favorite.target_type == target_type)
    items = query.order_by(Favorite.created_at.desc()).all()
    return success([{
        "id": f.id,
        "target_type": f.target_type,
        "target_id": f.target_id,
        "created_at": str(f.created_at) if f.created_at else None,
    } for f in items])

@router.get("/check")
def check_favorite(
    target_type: str,
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 检查是否已收藏
    fav = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.target_type == target_type,
        Favorite.target_id == target_id,
    ).first()
    return success({"favorited": bool(fav)})
