# 评论请求/响应模型
from pydantic import BaseModel
from datetime import datetime

class CommentCreate(BaseModel):
    target_type: str          # "article" 或 "post"
    target_id: int
    content: str
    parent_id: int = 0         # 0=一级评论

class CommentResponse(BaseModel):
    id: int
    user_id: int
    target_type: str
    target_id: int
    content: str
    parent_id: int
    created_at: datetime

    class Config:
        from_attributes = True
