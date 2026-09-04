
# AI Agent 请求/响应模型
# """""
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str           # 用户输入的内容

class ChatResponse(BaseModel):
    
    reply: str             # 回复内容
    tool_used: str = ""    # 调用了哪个工具（用于前端展示 Agent 行为）
    conversation_id: int = 0
