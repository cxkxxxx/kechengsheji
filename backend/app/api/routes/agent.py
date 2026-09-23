import os
import uuid
import json

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import UPLOAD_DIR
from app.models.user import User
from app.models.chat_record import ChatRecord
from app.schemas.agent import ChatRequest, ChatResponse
from app.utils.response import success
from app.agent.engine import run_agent, run_agent_stream

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
):
    # AI Agent 流式对话接口
    # 1. 保存用户消息
    # 2. 调用 Agent 引擎（流式，按智能体角色），逐片返回 SSE
    # 3. 结束前把完整回复保存到对话记录
    user_msg = ChatRecord(user_id=current_user.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    acc = {"reply": "", "tool_used": "chat", "saved": False}

    def generate():
        for evt in run_agent_stream(current_user.id, req.message, db, req.image_urls, req.agent):
            t = evt["type"]
            if t == "chunk":
                acc["reply"] += evt["text"]
                yield _sse({"type": "chunk", "text": evt["text"]})
            elif t == "meta":
                acc["tool_used"] = evt["tool_used"]
                yield _sse({"type": "meta", "tool_used": evt["tool_used"]})
            elif t == "done":
                agent_msg = ChatRecord(
                    user_id=current_user.id,
                    role="assistant",
                    content=acc["reply"],
                    tool_calls=acc["tool_used"],
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


@router.post("/upload")
def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    # 上传图片（AI 助手使用），保存到静态目录
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    fname = uuid.uuid4().hex + ext
    path = os.path.join(UPLOAD_DIR, fname)
    content = file.file.read()
    with open(path, "wb") as f:
        f.write(content)
    return success({
        "filename": fname,
        "url": f"/static/{fname}",
    })


@router.post("/chat-sync")
def chat_sync(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 非流式对话（保留，便于测试/兼容）
    user_msg = ChatRecord(user_id=current_user.id, role="user", content=req.message)
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
    )
    db.add(agent_msg)
    db.commit()

    return success(ChatResponse(
        reply=reply,
        tool_used=tool_used,
        conversation_id=user_msg.id,
    ))