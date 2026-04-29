# app\domains\knowledge\repository.py
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from sqlalchemy import text

from app.core.config import settings
from app.infra.database.session import SessionLocal
from app.utils.time_utils import now_kst

mongo_db = AsyncIOMotorClient(settings.MONGODB_URL)["meeting_assistant"]

# -------------------------------------------------------------
# MongoDB
# -------------------------------------------------------------
async def save_chat_log(workspace_id: int, session_id: str, role: str, content: str, function_type: str) -> None:
    await mongo_db["chatbot_logs"].insert_one({
        "workspace_id": workspace_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "function_type": function_type,
        "timestamp": now_kst()
    })

async def get_past_meetings_by_ids(meeting_ids: list[int]) -> list[dict]:
    """선택된 meeting_id 목록으로 이전 회의 요약 조회."""
    cursor = mongo_db["meeting_contexts"].find(
        {"meeting_id": {"$in": meeting_ids}},
        {"_id": 0}
    ).sort("created_at", 1) # 날짜 오름차순 (오래된 것 먼저)
    return await cursor.to_list(length=None)

async def get_all_past_meetings_by_workspace(workspace_id: int) -> list[dict]:
    """workspace_id 기준 전체 이전 회의 조회 (선택 안 했을 때 fallback)."""
    cursor = mongo_db["meeting_contexts"].find(
        {"$or": [
            {"workspace_id": workspace_id},
            {"workspace_id": {"$exists": False}},
        ]},
        {"_id": 0}
    ).sort("created_at", 1)
    return await cursor.to_list(length=None)

async def get_past_meetings(workspace_id: int) -> list[dict]:
    """
    워크스페이스 이전 회의 목록 반환.
    workspace_id 없는 문서도 포함 - 기존 seed 데이터 하위 호환용.
    """
    cursor = mongo_db["meeting_contexts"].find(
        {"$or": [
            {"workspace_id": workspace_id},
            {"workspace_id": {"$exists": False}}, # 구버전 데이터 호환
        ]},
        {"_id": 0, "meeting_id": 1, "title": 1, "created_at": 1}
    ).sort("created_at", -1)
    return await cursor.to_list(length=None)

async def get_past_meeting_ids(workspace_id: int) -> list[dict]:
    cursor = mongo_db["meeting_contexts"].find(
        {"$or": [
            {"workspace_id": workspace_id},
            {"workspace_id": {"$exists": False}}, # 구버전 데이터 호환
        ]},
        {"_id": 0, "meeting_id": 1}
    ).sort("created_at", -1)

    docs = await cursor.to_list(length=None)

    return [doc["meeting_id"] for doc in docs]

async def get_chat_history(workspace_id: int, session_id: str) -> list[dict]:
    cursor = mongo_db["chatbot_logs"].find(
        {"workspace_id": workspace_id, "session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1)
    return await cursor.to_list(length=None)


async def save_meeting_summary(workspace_id: int, meeting_id: int, summary: dict) -> None:
    """
    회의 요약을 meeting_summaries 컬렉션에 저장.

    upsert 사용 이유:
        회의 중간에 요약을 여러 번 호출할 수 있음.
        같은 meeting_id로 insert하면 중복 문서 생성 -> 최신 요약으로 덮어씀.

    updated_at을 을 별도로 두는 이유:
        최초 생성 시각(created_at)과 마지막 갱신 시각(updated_at)을 구분해
        "이 요약이 언제 처음 만들어졌고 마지막으로 언제 업데이트됐는지" 추적 가능.
    """
    now = now_kst()
    await mongo_db["meeting_summaries"].update_one(
        {"meeting_id": meeting_id},
        {
            "$set": {
                "workspace_id": workspace_id,
                "summary": summary,
                "attendees": summary.get("attendees", []),
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            }
        },
        upsert=True
    )

# -------------------------------------------------------------
# MySQL
# -------------------------------------------------------------
def get_meeting_participants(meeting_id: int) -> list[str]:
    """
    meeting_participants JOIN users로 참석자 이름 목록 반환

    is_host=True인 참석자를 앞에 정렬해                                                                                  
      "김철수(호스트), 이민준, 박지수" 형태로 표시 가능하게 함
    """
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT u.name, mp.is_host
                FROM meeting_participants mp
                JOIN users u ON mp.user_id = u.id
                WHERE mp.meeting_id = :meeting_id
                ORDER BY mp.is_host DESC, u.name ASC
            """),
            {"meeting_id": int(meeting_id)}
        ).fetchall()
        return [row.name for row in rows]
    finally:
        db.close()

def get_workspace_id(meeting_id: int) -> int:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT workspace_id
                FROM meetings
                WHERE id = :meeting_id
            """),
            {"meeting_id": int(meeting_id)}
        ).fetchone()
        return row.workspace_id if row else None
    finally:
        db.close()

def get_user_name_by_id(user_id: int) -> str | None:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        return row.name if row else None
    finally:
        db.close()