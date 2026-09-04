

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.utils.response import success

router = APIRouter()

@router.post("/login")
async def login(user_data: UserCreate, db: Session = Depends(get_db)):
    # # #     小程序登录流程：
# #     1. 前端 wx.login() 拿到 code
# #     2. 后端用 code 调微信 API 换 openid
# #     3. 查/建用户记录
# #     4. 返回 JWT token
# #     
    # TODO: 用 code 调微信 API 换 openid（需配置 AppID + AppSecret）
    # 开发阶段可先用 code 当作 openid 的简化方案
    openid = f"dev_{user_data.code[:16]}"

    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid, nickname=user_data.nickname, avatar=user_data.avatar)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return success({"token": token, "user": UserResponse.model_validate(user)})

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
        # 获取当前登录用户信息

    return success(UserResponse.model_validate(current_user))
