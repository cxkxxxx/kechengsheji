"""图片上传：社区帖子、攻略投稿、AI 助手识图共用一个入口。

安全口径只有一条：落盘的扩展名由文件真实字节决定，绝不用客户端传来的 filename 后缀。
/static 是公开可直接访问的目录，放过 .html / .svg 进来就等于给自己存了一个钓鱼页。
"""
import os
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import (UPLOAD_DIR, UPLOAD_MAX_BYTES, UPLOAD_MAX_MB,
                             SECRET_KEY, ALGORITHM)
from app.core.database import get_db
from app.core.rate_limit import hit as rate_hit
from app.models.admin import Admin
from app.models.user import User
from app.utils.response import success

router = APIRouter()

_EXT_BY_MAGIC = [
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
]
# webp 是 RIFF....WEBP，前 4 字节和一堆其它格式共用，要单独看第 8~12 字节
_WEBP_HEAD = b"RIFF"
_WEBP_TAG = b"WEBP"


def sniff(head: bytes) -> str:
    """按魔数判类型，认不出来就不是图片。"""
    for magic, ext in _EXT_BY_MAGIC:
        if head.startswith(magic):
            return ext
    if head.startswith(_WEBP_HEAD) and head[8:12] == _WEBP_TAG:
        return ".webp"
    return ""


def get_uploader(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    """小程序用户和管理端都能传图（后台要传攻略封面）。

    不能直接复用 get_current_user：两套 token 的 sub 形状不同，用户是纯数字、
    管理员是 "admin:<id>"，拿 int() 去解管理员 token 会直接 401。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    try:
        sub = str(jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM]).get("sub") or "")
    except JWTError:
        raise HTTPException(401, "登录已过期，请重新登录")
    if sub.startswith("admin:"):
        try:
            aid = int(sub.split(":")[1])
        except (IndexError, ValueError):
            raise HTTPException(401, "登录状态异常，请重新登录")
        if not db.query(Admin).filter(Admin.id == aid).first():
            raise HTTPException(401, "管理员不存在")
        return sub
    try:
        uid = int(sub)
    except ValueError:
        raise HTTPException(401, "登录状态异常，请重新登录")
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(401, "登录已过期，请重新登录")
    return sub


@router.post("/image")
async def upload_image(file: UploadFile = File(...), who: str = Depends(get_uploader)):
    # 限流走 hit() 而不是 limit_by_user：那个依赖内部又去解了一次用户 token，
    # 管理员的 sub="admin:1" 会被它 int() 炸成 401，后台就永远传不了封面。
    rate_hit(("upload_image", "who", who), 30)
    # 只读上限+1 字节：真超限的上传体不会整个进内存
    content = await file.read(UPLOAD_MAX_BYTES + 1)
    if not content:
        raise HTTPException(400, "文件是空的")
    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(413, "图片超过 %.0fMB 上限" % UPLOAD_MAX_MB)
    ext = sniff(content[:16])
    if not ext:
        raise HTTPException(415, "只接受 jpg / png / gif / webp 图片")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = uuid.uuid4().hex + ext
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
        f.write(content)
    return success({"filename": fname, "url": "/static/%s" % fname})
