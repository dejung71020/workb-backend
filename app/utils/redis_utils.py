# app/utils/redis_utils.py
import redis
import json
from pymongo import MongoClient

from app.core.config import settings

mongo_db = MongoClient(settings.MONGODB_URL)["workb"]

r = redis.from_url(settings.REDIS_URL)

def get_meeting_context(meeting_id: str) -> str:
    """전체 발화 컨텍스트 문자열 반환"""
    utterances_raw = r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)
    speakers = {
        k.decode(): v.decode()
        for k, v in r.hgetall(f"meeting:{meeting_id}:speakers").items()
    }
    lines = []
    for u in utterances_raw:
        utterance = json.loads(u)
        name = speakers.get(utterance["speaker_id"], utterance["speaker_id"])
        lines.append(f"[{name}] {utterance['content']}")
    return "\n".join(lines)


def get_related_utterance(meeting_id: str, seq: int | None) -> str:
    """seq 기준 단일 발화 반환"""
    if seq is None:
        return ""

    utterances_raw = r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)
    speakers = {
        k.decode(): v.decode()
        for k, v in r.hgetall(f"meeting:{meeting_id}:speakers").items()
    }

    if seq < len(utterances_raw):
        utterance = json.loads(utterances_raw[seq])
        name = speakers.get(utterance["speaker_id"], utterance["speaker_id"])
        return f"[{name}] {utterance['content']}"
    return ""

def get_past_meeting_context(meeting_id: str) -> str:
    """MongoDB meeting_contexts에서 이전 회의 컨텍스트 가져오기"""
    doc = mongo_db["meeting_contexts"].find_one({"meeting_id": meeting_id})
    if doc:
        return doc.get("summary", "")
    return ""