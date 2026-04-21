# app\domains\knowledge\repository.py
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from sqlalchemy import text

from app.core.config import settings
from app.infra.database.session import SessionLocal

mongo_db = AsyncIOMotorClient(settings.MONGODB_URL)["workb"]

# -------------------------------------------------------------
# MongoDB
# -------------------------------------------------------------
async def save_chat_log(meeting_id: str, session_id: str, role: str, content: str, function_type: str) -> None:
    await mongo_db["chatbot_logs"].insert_one({
        "meeting_id": meeting_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "function_type": function_type,
        "timestamp": datetime.now()
    })

async def get_chat_history(meeting_id: str, session_id: str) -> list[dict]:
    cursor = await mongo_db["chatbot_logs"].find(
        {"meeting_id": meeting_id, "session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1)
    return list(cursor)


async def save_meeting_summary(meeting_id: str, summary: dict) -> None:
    """
    회의 요약을 meeting_summaries 컬렉션에 저장.

    upsert 사용 이유:
        회의 중간에 요약을 여러 번 호출할 수 있음.
        같은 meeting_id로 insert하면 중복 문서 생성 -> 최신 요약으로 덮어씀.

    updated_at을 을 별도로 두는 이유:
        최초 생성 시각(created_at)과 마지막 갱신 시각(updated_at)을 구분해
        "이 요약이 언제 처음 만들어졌고 마지막으로 언제 업데이트됐는지" 추적 가능.
    """
    now = datetime.now()
    await mongo_db["meeting_summaries"].update_one(
        {"meeting_id": meeting_id},
        {
            "$set": {
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
def get_meeting_participants(meeting_id: str) -> list[str]:
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