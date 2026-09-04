# 攻略文章请求/响应模型
""
from pydantic import BaseModel

class ArticleResponse(BaseModel):
    id: int
    title: str
    content: str = ""
    category: str
    cover: str = ""
    author: str
    likes: int
    views: int

    class Config:
        from_attributes = True
