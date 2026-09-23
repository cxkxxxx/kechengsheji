

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.post_like import PostLike
from app.schemas.post import PostCreate, PostResponse
from app.utils.response import success

router = APIRouter()

@router.get("")
def get_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    items = db.query(Post).filter(Post.status == "approved") \
        .order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    return success([PostResponse.model_validate(p) for p in items])

@router.post("")
def create_post(
    post_data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = Post(
        user_id=current_user.id,
        title=post_data.title,
        content=post_data.content,
        images=post_data.images,
        tags=post_data.tags,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return success(PostResponse.model_validate(post))

@router.get("/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id, Post.status == "approved").first()
    if not post:
        return success(None, "帖子不存在")
    return success(PostResponse.model_validate(post))

@router.post("/{post_id}/like")
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 切换点赞状态（toggle）
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return success(None, "帖子不存在")

    existing = db.query(PostLike).filter(
        PostLike.user_id == current_user.id,
        PostLike.post_id == post_id,
    ).first()

    if existing:
        # 已点赞 → 取消
        db.delete(existing)
        post.likes = max(0, post.likes - 1)
        liked = False
    else:
        # 未点赞 → 点赞
        db.add(PostLike(user_id=current_user.id, post_id=post_id))
        post.likes += 1
        liked = True

    db.commit()
    db.refresh(post)
    return success({"likes": post.likes, "liked": liked})
