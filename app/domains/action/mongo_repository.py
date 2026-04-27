# app/domains/action/mongo_repository.py
from pymongo import MongoClient
from app.core.config import settings

mongo_db = MongoClient(settings.MONGODB_URL)['meeting_assistant']

def get_meeting_summary(meeting_id: int) -> dict:
    doc = mongo_db['meeting_summaries'].find_one({
        "meeting_id": meeting_id,
    })
    return doc['summary'] if doc else {}