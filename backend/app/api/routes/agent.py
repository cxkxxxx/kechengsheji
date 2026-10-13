import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.rate_limit import limit_by_user
from app.models.user import User
from app.models.chat_record import ChatRecord
from app.schemas.agent import ChatRequest, ChatResponse
from app.utils.response import success
from app.agent.engine import run_agent, run_agent_stream
from app.agent.memory import list_history, clear_history
from app.agent.roles import DEFAULT_AGENT

router = APIRouter()


def _sse(obj) -> str:
    # 把字典序列化成一行 SSE：data: {...}\n\n
    # 必须用 ASCII 转义：中文原样上线时，网络分块可能切在多字节中间导致前端解码乱码
    return "data: " + json.dumps(obj) + "\n\n"


@router.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(limit_by_user("agent_chat")),
):
    # AI Agent 流式对话接口
    # 1. 保存用户消息
    # 2. 调用 Agent 引擎（流式，按智能体角色），逐片返回 SSE
    # 3. 结束前把完整回复保存到对话记录
    user_msg = ChatRecord(user_id=current_user.id, role="user", content=req.message, agent=req.agent)
    db.add(user_msg)
    db.commit()

    acc = {"reply": "", "tool_used": "chat", "links": [], "tables": [], "saved": False}

    def generate():
        for evt in run_agent_stream(current_user.id, req.message, db, req.image_urls, req.agent):
            t = evt["type"]
            if t == "chunk":
                acc["reply"] += evt["text"]
                yield _sse({"type": "chunk", "text": evt["text"]})
            elif t == "meta":
                acc["tool_used"] = evt["tool_used"]
                yield _sse({"type": "meta", "tool_used": evt["tool_used"]})
            elif t == "links":
                # 卡片既随流式下发，也存进这条回复，重进小程序后仍能看到并复制
                acc["links"] = evt["items"]
                yield _sse({"type": "links", "items": evt["items"]})
            elif t == "tables":
                acc["tables"] = evt["items"]
                yield _sse({"type": "tables", "items": evt["items"]})
            elif t == "done":
                agent_msg = ChatRecord(
                    user_id=current_user.id,
                    role="assistant",
                    content=acc["reply"],
                    tool_calls=acc["tool_used"],
                    links=json.dumps(acc["links"], ensure_ascii=False) if acc["links"] else None,
                    tables=json.dumps(acc["tables"], ensure_ascii=False) if acc["tables"] else None,
                    tokens_used=int(evt.get("tokens_used") or 0),
                    agent=req.agent,
                )
                db.add(agent_msg)
                db.commit()
                acc["saved"] = True
                yield _sse({"type": "done", "conversation_id": user_msg.id})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
def get_history(
    agent: str = DEFAULT_AGENT,
    limit: int = 40,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 拉回某个智能体的对话记录：小程序重进后界面还能接着上次看
    limit = max(1, min(limit, 100))
    return success({"agent": agent, "messages": list_history(current_user.id, db, agent, limit)})


@router.delete("/history")
def delete_history(
    agent: str = DEFAULT_AGENT,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 清空该智能体的记忆（只清当前这个专家，不影响其它两个）
    deleted = clear_history(current_user.id, db, agent)
    db.commit()
    return success({"agent": agent, "deleted": deleted})


@router.post("/chat-sync")
def chat_sync(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(limit_by_user("agent_chat")),
):
    # 非流式对话（保留，便于测试/兼容）
    user_msg = ChatRecord(user_id=current_user.id, role="user", content=req.message, agent=req.agent)
    db.add(user_msg)
    db.commit()

    reply, tool_used = run_agent(
        user_id=current_user.id,
        message=req.message,
        db=db,
        agent=req.agent,
    )

    agent_msg = ChatRecord(
        user_id=current_user.id,
        role="assistant",
        content=reply,
        tool_calls=tool_used,
        agent=req.agent,
    )
    db.add(agent_msg)
    db.commit()

    return success(ChatResponse(
        reply=reply,
        tool_used=tool_used,
        conversation_id=user_msg.id,
    ))