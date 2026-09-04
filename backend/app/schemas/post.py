
# 社区帖子请求/响应模型
# """""
from pydantic import BaseModel

class PostCreate(BaseModel):
    title: str
    content: str
    images: str = ""       # JSON 字符串
    tags: str = ""

class PostResponse(BaseModel):
    id: int
    user_id: int
    title: str
    content: str
    images: str = ""
    tags: str = ""
    likes: int
    comments_count: int

    class Config:
        from_attributes = True
