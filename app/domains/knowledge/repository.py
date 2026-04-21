# app\domains\knowledge\repository.py
from pymongo import MongoClient
from datetime import datetime
from app.core.config import settings

mongo_db = MongoClient(settings.MONGODB_URL)["workb"]

def save_chat_log(meeting_id: str, session_id: str, role: str, content: str, function_type: str) -> None:
    mongo_db["chatbot_logs"].insert_one({
        "meeting_id": meeting_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "function_type": function_type,
        "timestamp": datetime.now()
    })

def get_chat_history(meeting_id: str, session_id: str) -> list[dict]:
    cursor = mongo_db["chatbot_logs"].find(
        {"meeting_id": meeting_id, "session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1)
    return list(cursor)