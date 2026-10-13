# 社区帖子请求/响应模型
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import List, Optional

from app.utils import images as image_field


class PostCreate(BaseModel):
    title: str
    content: str
    images: List[str] = []     # /upload/image 返回的 /static/ 地址，最多 9 张
    tags: str = ""

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("标题不能为空")
        return v[:200]


class PostResponse(BaseModel):
    id: int
    user_id: int
    title: str
    content: str
    images: List[str] = []
    tags: Optional[str] = None
    likes: int
    comments_count: int
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator("images", mode="before")
    @classmethod
    def _parse_images(cls, v):
        return image_field.loads(v if isinstance(v, str) else None)
