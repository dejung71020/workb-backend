# app/domains/action/mongo_repository.py
from pymongo import MongoClient
from app.core.config import settings

mongo_db = MongoClient(settings.MONGODB_URL)['meeting_assistant']


def get_meeting_summary(meeting_id: int) -> dict | None:
    doc = mongo_db['meeting_summaries'].find_one({"meeting_id": meeting_id})
    if not doc:
        return None
    return doc.get('summary') or None


def get_meeting_utterances(meeting_id: int) -> list[dict]:
    """utterances 컬렉션에서 발화 목록을 반환합니다. 없으면 빈 리스트."""
    doc = mongo_db['utterances'].find_one(
        {"$or": [{"meeting_id": meeting_id}, {"meeting_id": str(meeting_id)}]},
        {"_id": 0, "utterances": 1},
    )
    return doc.get("utterances", []) if doc else []