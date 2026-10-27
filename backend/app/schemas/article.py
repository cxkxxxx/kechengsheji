# 攻略文章请求/响应模型
from pydantic import BaseModel, field_validator
from typing import List, Optional

from app.utils import images as image_field


class ArticleCreate(BaseModel):
    """用户投稿 / 管理端发文共用。图片走 /upload/image 拿到 /static/ 地址后再提交。"""
    title: str
    content: str = ""
    category: str = "综合"
    cover: str = ""
    images: List[str] = []
    # 可选：这稿子如果来自 AI 创作助手，带上 creation_id，发布成功后回填
    # ai_creations.article_id，历史里就能区分「未发布草稿 / 已发布攻略」
    creation_id: Optional[int] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("标题不能为空")
        return v[:200]


class ArticleResponse(BaseModel):
    id: int
    title: str
    content: str = ""
    category: str
    cover: Optional[str] = None
    images: List[str] = []
    author: str
    likes: int
    views: int

    class Config:
        from_attributes = True

    @field_validator("images", mode="before")
    @classmethod
    def _parse_images(cls, v):
        # 库里存的是 JSON 字符串，接口对外给数组，别让每个前端各自 JSON.parse
        return image_field.loads(v if isinstance(v, str) else None)
