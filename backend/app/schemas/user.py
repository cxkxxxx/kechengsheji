

from pydantic import BaseModel

class UserCreate(BaseModel):
    # # 小程序登录请求（传 code，后端换 openid）
    code: str           # 微信 wx.login() 获取的 code
    nickname: str = "省钱达人"
    avatar: str = ""

class UserResponse(BaseModel):
        # 返回给前端的用户信息

    id: int
    nickname: str
    avatar: str
    budget_goal: float
    total_saved: float

    class Config:
        from_attributes = True
