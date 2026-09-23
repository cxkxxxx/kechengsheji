
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.comment import Comment
from app.models.post import Post
from app.models.article import Article
from app.schemas.comment import CommentCreate, CommentResponse
from app.utils.response import success

router = APIRouter()

@router.get("")
def get_comments(
    target_type: str,
    target_id: int,
    db: Session = Depends(get_db),
):
    # 获取某文章/帖子的评论列表
    items = db.query(Comment).filter(
        Comment.target_type == target_type,
        Comment.target_id == target_id,
    ).order_by(Comment.created_at.desc()).all()
    return success([CommentResponse.model_validate(c) for c in items])

@router.post("")
def create_comment(
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 发表评论
    comment = Comment(
        user_id=current_user.id,
        target_type=data.target_type,
        target_id=data.target_id,
        content=data.content,
        parent_id=data.parent_id,
    )
    db.add(comment)
    # 帖子评论数 +1
    if data.target_type == "post":
        post = db.query(Post).filter(Post.id == data.target_id).first()
        if post:
            post.comments_count = (post.comments_count or 0) + 1
    db.commit()
    db.refresh(comment)
    return success(CommentResponse.model_validate(comment))

@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 删除自己的评论
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return success(None, "评论不存在")
    if comment.user_id != current_user.id:
        return success(None, "无权删除他人评论")
    if comment.target_type == "post":
        post = db.query(Post).filter(Post.id == comment.target_id).first()
        if post and post.comments_count and post.comments_count > 0:
            post.comments_count -= 1
    db.delete(comment)
    db.commit()
    return success(None, "删除成功")
