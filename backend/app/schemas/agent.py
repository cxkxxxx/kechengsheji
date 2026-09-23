# AI Agent 请求/响应模型
from pydantic import BaseModel, Field
from typing import List

class ChatRequest(BaseModel):
    message: str                                  # 用户输入的内容
    image_urls: List[str] = Field(default_factory=list)   # 用户随消息上传的图片(文件名或URL)
    agent: str = "default"                        # 智能体角色：default/coupon/budget

class ChatResponse(BaseModel):
    reply: str             # 回复内容
    tool_used: str = ""    # 调用了哪个工具（用于前端展示 Agent 行为）
    conversation_id: int = 0