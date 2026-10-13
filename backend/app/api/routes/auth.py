
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (create_access_token, get_current_user,
                               hash_password, verify_password)
from app.core.config import WX_APPID, WX_SECRET
from app.core.rate_limit import limit_by_ip
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserRegister, UserResponse
from app.utils.response import success

router = APIRouter()

WX_SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
# 微信侧的错误码翻译成一句人话，别把 errcode 原样丢给用户
WX_ERRORS = {
    "-1": "微信服务暂时不可用，请稍后再试",
    "40013": "AppID 不正确，检查 .env 的 WX_APPID",
    "40029": "登录凭证无效（code 只能用一次且几分钟内失效），请重新进入小程序",
    "45011": "登录过于频繁，请稍后再试",
}

_NICK_RE = re.compile(r"^[\w\u4e00-\u9fa5\-·]{2,20}$")


def wx_login_ready() -> bool:
    return bool(WX_APPID and WX_SECRET)


def _issue(user: User):
    return success({"token": create_access_token({"sub": str(user.id)}),
                    "user": UserResponse.model_validate(user)})


def _clean_nickname(nickname: str) -> str:
    nickname = (nickname or "").strip()
    if not _NICK_RE.match(nickname):
        raise HTTPException(400, "昵称 2-20 个字，只能用中文、字母、数字、- 和 ·")
    return nickname


def _by_nickname(nickname: str, db: Session):
    """按昵称找密码账号。

    只认设过密码的行：历史上 wx 登录会按 code 建一堆同名用户，
    拿 nickname 全局查 first() 可能登进别人的账号。
    """
    return (db.query(User)
            .filter(User.nickname == nickname, User.password_hash.isnot(None))
            .order_by(User.id).first())


@router.get("/config")
def auth_config():
    # 登录页据此决定显示「微信一键登录」还是「昵称密码」，避免前端写死
    return success({"wx_login": wx_login_ready()})


@router.post("/register")
def register(req: UserRegister, db: Session = Depends(get_db),
             _: None = Depends(limit_by_ip("auth_register", limit=5))):
    nickname = _clean_nickname(req.nickname)
    if len(req.password or "") < 6:
        raise HTTPException(400, "密码至少 6 位")
    if len(req.password) > 72:
        raise HTTPException(400, "密码太长了")
    if _by_nickname(nickname, db):
        raise HTTPException(409, "该昵称已注册，换个昵称或直接登录")
    user = User(openid=None, nickname=nickname, avatar="",
                password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(user)


@router.post("/login-password")
def login_password(req: UserLogin, db: Session = Depends(get_db),
                   _: None = Depends(limit_by_ip("auth_login", limit=10))):
    # 防爆破靠 IP 限流；密码比对用 bcrypt，恒定时间
    user = _by_nickname((req.nickname or "").strip(), db)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "昵称或密码不正确")
    return _issue(user)


@router.post("/login")
async def login(user_data: UserCreate, db: Session = Depends(get_db),
                _: None = Depends(limit_by_ip("auth_login", limit=30))):
    """微信正式登录：code 换 openid，再查/建用户。

    以前这里写的是 openid = f"dev_{code[:16]}"。wx.login 每次返回的 code 都不一样，
    等于每次登录都新建一个用户 —— 「我的发帖」永远同步不上就是这个原因。
    没配 WX_SECRET 时宁可明确报错，也不再伪造身份。
    """
    if not wx_login_ready():
        raise HTTPException(501, "服务端未配置 WX_APPID / WX_SECRET，微信登录不可用，请用昵称密码登录")

    params = {"appid": WX_APPID, "secret": WX_SECRET,
              "js_code": user_data.code, "grant_type": "authorization_code"}
    try:
        r = await httpx.AsyncClient(timeout=8).get(WX_SESSION_URL, params=params)
        data = r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "连不上微信登录服务，请检查网络后重试")

    openid = data.get("openid")
    if not openid:
        code = str(data.get("errcode"))
        raise HTTPException(401, WX_ERRORS.get(code, "微信登录失败（errcode=%s）" % code))

    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid, nickname=(user_data.nickname or "").strip()[:50] or "微信用户",
                    avatar=user_data.avatar or "")
        db.add(user)
        db.commit()
        db.refresh(user)
    return _issue(user)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    # 获取当前登录用户信息
    return success(UserResponse.model_validate(current_user))
