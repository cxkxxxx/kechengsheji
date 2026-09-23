# 社区帖子请求/响应模型
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

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
    images: Optional[str] = None
    tags: Optional[str] = None
    likes: int
    comments_count: int
    created_at: datetime

    class Config:
        from_attributes = True
