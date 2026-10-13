# AI Agent 请求/响应模型
from pydantic import BaseModel, Field, model_validator
from typing import List

from app.agent.roles import DEFAULT_AGENT, normalize


class ChatRequest(BaseModel):
    message: str                                  # 用户输入的内容
    image_urls: List[str] = Field(default_factory=list)   # 用户随消息上传的图片(文件名或URL)
    agent: str = DEFAULT_AGENT                    # 智能体角色：coupon / budget

    @model_validator(mode="after")
    def _require_content(self):
        # 空 prompt 智谱会回 400（1213 未正常接收到prompt参数），白烧一次请求，
        # 用户还只能看到「服务暂时不可用」。只允许「有文字」或「只发图」两种。
        has_image = any((u or "").strip() for u in self.image_urls)
        if not self.message.strip() and not has_image:
            raise ValueError("消息不能为空")
        self.agent = normalize(self.agent)
        return self

class ChatResponse(BaseModel):
    reply: str             # 回复内容
    tool_used: str = ""    # 调用了哪个工具（用于前端展示 Agent 行为）
    conversation_id: int = 0