# 攻略文章请求/响应模型
from pydantic import BaseModel
from typing import Optional

class ArticleResponse(BaseModel):
    id: int
    title: str
    content: str = ""
    category: str
    cover: Optional[str] = None
    author: str
    likes: int
    views: int

    class Config:
        from_attributes = True
