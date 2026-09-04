

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.chat_record import ChatRecord
from app.schemas.agent import ChatRequest, ChatResponse
from app.utils.response import success
from app.agent.engine import run_agent

router = APIRouter()

@router.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # # #     AI Agent 对话接口
# #     1. 保存用户消息到对话记录
# #     2. 调用 Agent 引擎（意图识别 → 工具调用 → 生成回复）
# #     3. 保存 Agent 回复到对话记录
# #     4. 返回回复内容 + 调用的工具名
# #     
    # 保存用户消息
    user_msg = ChatRecord(user_id=current_user.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # 调用 Agent 引擎
    reply, tool_used = run_agent(
        user_id=current_user.id,
        message=req.message,
        db=db,
    )

    # 保存 Agent 回复
    agent_msg = ChatRecord(
        user_id=current_user.id,
        role="assistant",
        content=reply,
        tool_calls=tool_used,
    )
    db.add(agent_msg)
    db.commit()

    return success(ChatResponse(
        reply=reply,
        tool_used=tool_used,
        conversation_id=user_msg.id,
    ))
