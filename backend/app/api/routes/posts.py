

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import POST_MAX_IMAGES
from app.models.user import User
from app.models.post import Post
from app.models.post_like import PostLike
from app.schemas.post import PostCreate, PostResponse
from app.utils import images as image_field
from app.utils.response import success

router = APIRouter()

@router.get("")
def get_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    # 内容流只放行已过审的帖子；作者昵称/头像一并 join 带出来，
    # 参考成熟社区的做法——卡片第一行是「谁在什么时候发的」
    rows = (db.query(Post, User.nickname, User.avatar)
            .outerjoin(User, Post.user_id == User.id)
            .filter(Post.status == "approved")
            .order_by(Post.created_at.desc()).offset(skip).limit(limit).all())
    items = []
    for p, nickname, avatar in rows:
        m = PostResponse.model_validate(p).model_dump()
        m["author"] = (nickname or "").strip() or "省钱用户"
        m["author_avatar"] = avatar or ""
        items.append(m)
    return success(items)

@router.get("/mine")
def my_posts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 我自己的帖子必须走这个接口，不能拿 GET /posts 去前端挑：
    # 那个只返回全局最新 20 条已过审的，用户第 21 条和被打回的帖子永远不在里面，
    # 「我的发帖」数量自然对不上、列表还经常是空的。
    rows = (db.query(Post).filter(Post.user_id == current_user.id)
            .order_by(Post.created_at.desc()).limit(100).all())
    items = [PostResponse.model_validate(p).model_dump() for p in rows]
    for p, m in zip(rows, items):
        m["status"] = p.status or "approved"
    return success({"total": len(items),
                    "published": sum(1 for p in rows if (p.status or "approved") == "approved"),
                    "items": items})


@router.post("")
def create_post(
    post_data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        images = image_field.dumps(post_data.images, POST_MAX_IMAGES, "图片")
    except ValueError as e:
        raise HTTPException(400, str(e))
    post = Post(
        user_id=current_user.id,
        title=post_data.title,
        content=post_data.content,
        images=images,
        tags=post_data.tags,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return success(PostResponse.model_validate(post))

@router.get("/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    row = (db.query(Post, User.nickname, User.avatar)
           .outerjoin(User, Post.user_id == User.id)
           .filter(Post.id == post_id, Post.status == "approved").first())
    if not row:
        return success(None, "帖子不存在")
    p, nickname, avatar = row
    m = PostResponse.model_validate(p).model_dump()
    m["author"] = (nickname or "").strip() or "省钱用户"
    m["author_avatar"] = avatar or ""
    return success(m)

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
