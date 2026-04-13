# app\domains\knowledge\router.py
from fastapi import APIRouter
from datetime import datetime
from uuid import uuid4

from app.core.graph.workflow import knowledge_app
from app.domains.knowledge.schemas import ChatbotMessageRequest

router = APIRouter()

@router.post("/meetings/{meeting_id}/chatbot/message")
async def chatbot_message(meeting_id: str, req: ChatbotMessageRequest):
    state = {
        "meeting_id": meeting_id,
        "user_question": req.message,
        "function_type": "",
        "chat_response": ""
    }
    result = knowledge_app.invoke(state)

    return {
        "session_id": f"{meeting_id}-{uuid4()}",
        "function_type": result["function_type"],
        "answer": result["chat_response"],
        "result": {},
        "timestamp": datetime.now()
    }