# app\domains\knowledge\schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ChatbotMessageRequest(BaseModel):
    message: str
    session_id: str

class ChatbotMessageResponse(BaseModel):
    session_id: str
    function_type: str
    answer: str
    result: str
    timestamp: datetime

class ChatbotSummaryResponse(BaseModel):
    summary: str
    generated_at: datetime

class ChatbotHistoryMessage(BaseModel):
    role: str
    content: str
    function_type: str
    timestamp: datetime

class ChatbotHistoryResponse(BaseModel):
    messages: list[ChatbotHistoryMessage]