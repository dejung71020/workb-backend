# app\domains\knowledge\schemas.py
from pydantic import BaseModel
from datetime import datetime

class ChatbotMessageRequest(BaseModel):
    message: str

class ChatbotMessageResponse(BaseModel):
    session_id: str
    function_type: str
    answer: str
    result: str
    timestamp: datetime