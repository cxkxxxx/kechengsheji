

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.post import Post
from app.schemas.post import PostCreate, PostResponse
from app.utils.response import success

router = APIRouter()

@router.get("")
def get_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
        # 获取社区帖子列表

    items = db.query(Post).filter(Post.status == "approved") \
        .order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    return success([PostResponse.model_validate(p) for p in items])

@router.post("")
def create_post(
    post_data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 发布省钱经验帖

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
        # 获取帖子详情

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
        # 点赞社区帖子

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return success(None, "帖子不存在")
    post.likes += 1
    db.commit()
    db.refresh(post)
    return success({"likes": post.likes})