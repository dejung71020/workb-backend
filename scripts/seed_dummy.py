"""
seed_dummy.py - /docs 테스트용 더미 데이터 삽입

삽입 대상:
    - Redis: meeting:{id}:utterances, meeting:{id}:speakers, meeting:{id}:latest  (현재 회의 = meeting_id 4)
    - MongoDB: meeting_contexts (이전 회의 요약), utterances (이전 회의 raw 발화)  (meeting_id 2, 3)
    - MySQL: meetings (meeting_id 2, 3 = done, meeting_id 4 = in_progress)

실행:
    python scripts/seed_dummy.py
    python scripts/seed_dummy.py --flush   # 기존 데이터 삭제 후 재삽입
"""
import sys, os, json, argparse
import redis
from pymongo import MongoClient
from datetime import datetime
from sqlalchemy import create_engine, text

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.core.config import settings

# --- 클라이언트 ---
r = redis.from_url(settings.REDIS_URL)
mongo_db = MongoClient(settings.MONGODB_URL)["workb"]

# 현재 회의 ID (Redis 발화 + MySQL in_progress)
DEFAULT_MEETING_ID = "4"

# ------------------------------------------------------------------
# 더미 발화 데이터 (현재 회의 = meeting_id 4)
# ASR 서버 형식: speaker_id=int, speaker=이름(선택), content=발화내용
# ------------------------------------------------------------------
UTTERANCES = [
    {"speaker_id": "spk_01", "content": "오늘 회의 시작하겠습니다. 신규 백엔드 아키텍처 방향성 논의가 주요 안건입니다.", "timestamp": "2026-04-27T10:00:00"},
    {"speaker_id": "spk_02", "content": "FastAPI에서 Django로 마이그레이션하는 건 리소스 낭비인 것 같아요. 현행 유지가 낫지 않을까요?", "timestamp": "2026-04-27T10:01:00"},
    {"speaker_id": "spk_01", "content": "동의합니다. FastAPI 그대로 가되, 모듈 구조를 도메인별로 정리하는 방향으로 결정합시다.", "timestamp": "2026-04-27T10:02:00"},
    {"speaker_id": "spk_02", "content": "그러면 김철수 님이 도메인 분리 작업 맡아주실 수 있을까요? 이번 주 금요일까지 초안 부탁드립니다.", "timestamp": "2026-04-27T10:03:00"},
    {"speaker_id": "spk_01", "content": "Redis 캐시 TTL 설정 건은 아직 결론이 안 났죠? 다음 회의 전까지 검토 필요합니다.", "timestamp": "2026-04-27T10:04:00"},
    # speakers 해시에 없는 화자 → "화자1" (미매칭)
    {"speaker_id": "spk_03", "content": "인증 모듈 리팩토링은 ASAP으로 진행해야 할 것 같습니다. 보안 이슈가 있어요.", "timestamp": "2026-04-27T10:05:00"},
    {"speaker_id": "spk_03", "content": "JWT 토큰 만료 처리 로직이 현재 누락되어 있습니다. 반드시 이번 스프린트 안에 수정해야 합니다.", "timestamp": "2026-04-27T10:06:00"},
    # speaker_id 없음 → "알 수 없음"
    {"content": "데이터베이스 인덱스 최적화도 논의가 필요합니다.", "timestamp": "2026-04-27T10:07:00"},
    {"content": "다음 회의는 5월 4일 오전 10시로 잡겠습니다.", "timestamp": "2026-04-27T10:08:00"},
    {"speaker_id": "spk_01", "content": "이번 회의 정리하겠습니다. 도메인 분리는 김철수 님, 인증 모듈 수정은 이번 스프린트 필수, Redis TTL은 미결입니다.", "timestamp": "2026-04-27T10:09:00"},
]

# ASR 서버 speakers 해시: Field=spk_01, Value=user.id (매칭 성공한 화자만 저장)
SPEAKERS = {
    "spk_01": "1",  # user.id
    "spk_02": "2",  # user.id
    # spk_03 없음 → "화자1"으로 폴백
}

# meeting:{id}:latest — 화자분리 미확정 최신 발화 (ASR 스트리밍 중 가장 최근 인식 텍스트)
LATEST_TEXT = "데이터베이스 인덱스 최적화 방안에 대해서도 다음 회의 전에 한번 정리가 필요할 것 같습니다."

# ------------------------------------------------------------------
# MongoDB 이전 회의 요약 (meeting_id 2, 3) — meeting_contexts 컬렉션
# ------------------------------------------------------------------
PAST_MEETINGS = [
    {
        "meeting_id": 2,
        "workspace_id": 2,
        "title": "2026-04-10 스프린트 계획 회의",
        "summary": (
            "4월 스프린트 목표 설정 및 태스크 배분 논의. "
            "프론트엔드 컴포넌트 리팩토링 우선순위 높음으로 결정. "
            "액션 아이템: 이민준 - 컴포넌트 설계 문서 작성 (미완료), "
            "박지수 - API 명세서 업데이트 (완료). "
            "다음 회의에서 중간 점검 예정."
        ),
        "created_at": datetime(2026, 4, 10, 10, 0, 0),
    },
    {
        "meeting_id": 3,
        "workspace_id": 2,
        "title": "2026-04-17 백엔드 아키텍처 사전 논의",
        "summary": (
            "FastAPI 도메인 구조 개편 필요성에 대해 논의함. "
            "인증 모듈 JWT 토큰 만료 처리 누락 이슈 제기됨. "
            "액션 아이템: 김철수 - 도메인 분리 초안 작성 (미완료), "
            "이민준 - Redis TTL 정책 검토 (미완료). "
            "다음 회의에서 진행 상황 확인 예정."
        ),
        "created_at": datetime(2026, 4, 17, 10, 0, 0),
    },
]

# ------------------------------------------------------------------
# MongoDB 이전 회의 raw 발화 (meeting_id 2, 3) — utterances 컬렉션
# ASR 서버 스키마: 회의당 문서 1개, utterances 배열 nested
# 필드: seq(int), speaker_id(int), speaker_label(str), text(str), timestamp(str)
# ------------------------------------------------------------------
PAST_UTTERANCES = [
    {
        "meeting_id": 2,
        "workspace_id": 2,
        "created_at": datetime(2026, 4, 10, 10, 0, 0),
        "updated_at": datetime(2026, 4, 10, 11, 0, 0),
        "total_duration_sec": 660,
        "meeting_start_time": datetime(2026, 4, 10, 10, 0, 0),
        "utterances": [
            {"seq": 1, "speaker_id": 1, "speaker_label": "박지수", "text": "오늘은 4월 스프린트 목표와 태스크 배분을 논의하겠습니다.", "timestamp": "2026-04-10T10:00:00"},
            {"seq": 2, "speaker_id": 2, "speaker_label": "이민준", "text": "프론트엔드 컴포넌트 리팩토링을 이번 스프린트 최우선으로 잡아야 할 것 같아요.", "timestamp": "2026-04-10T10:02:00"},
            {"seq": 3, "speaker_id": 1, "speaker_label": "박지수", "text": "동의합니다. 이민준 님이 컴포넌트 설계 문서 작성 맡아주시면 좋겠어요.", "timestamp": "2026-04-10T10:05:00"},
            {"seq": 4, "speaker_id": 2, "speaker_label": "이민준", "text": "네, 제가 컴포넌트 설계 문서 작성하겠습니다. 언제까지 드려야 할까요?", "timestamp": "2026-04-10T10:06:00"},
            {"seq": 5, "speaker_id": 1, "speaker_label": "박지수", "text": "다음 회의 전까지 초안 주시면 됩니다. 저는 API 명세서 업데이트 진행하겠습니다.", "timestamp": "2026-04-10T10:08:00"},
            {"seq": 6, "speaker_id": 2, "speaker_label": "이민준", "text": "그리고 다음 회의에서 중간 점검 한 번 하는 게 좋겠습니다.", "timestamp": "2026-04-10T10:10:00"},
        ],
    },
    {
        "meeting_id": 3,
        "workspace_id": 2,
        "created_at": datetime(2026, 4, 17, 10, 0, 0),
        "updated_at": datetime(2026, 4, 17, 11, 0, 0),
        "total_duration_sec": 780,
        "meeting_start_time": datetime(2026, 4, 17, 10, 0, 0),
        "utterances": [
            {"seq": 1, "speaker_id": 1, "speaker_label": "박지수", "text": "FastAPI 도메인 구조를 전면 개편해야 한다는 의견이 있어서 오늘 논의하려고 합니다.", "timestamp": "2026-04-17T10:00:00"},
            {"seq": 2, "speaker_id": 3, "speaker_label": "김철수", "text": "현재 구조가 너무 flat해서 도메인별로 분리가 필요합니다. 제가 초안 작성할게요.", "timestamp": "2026-04-17T10:02:00"},
            {"seq": 3, "speaker_id": 2, "speaker_label": "이민준", "text": "인증 모듈에 JWT 토큰 만료 처리 로직이 누락된 것 발견했습니다. 보안상 심각한 이슈입니다.", "timestamp": "2026-04-17T10:05:00"},
            {"seq": 4, "speaker_id": 1, "speaker_label": "박지수", "text": "JWT 토큰 만료 처리는 이번 스프린트 안에 반드시 수정해야 합니다.", "timestamp": "2026-04-17T10:07:00"},
            {"seq": 5, "speaker_id": 2, "speaker_label": "이민준", "text": "Redis TTL 정책도 아직 결정이 안 났는데, 제가 검토해서 다음 회의 때 보고하겠습니다.", "timestamp": "2026-04-17T10:10:00"},
            {"seq": 6, "speaker_id": 3, "speaker_label": "김철수", "text": "도메인 분리 초안은 이번 주 금요일까지 작성해서 공유하겠습니다.", "timestamp": "2026-04-17T10:12:00"},
        ],
    },
]


def seed_mysql(meeting_id: int, workspace_id: int, flush: bool):
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        if flush:
            past_ids = [m["meeting_id"] for m in PAST_MEETINGS]
            all_ids = past_ids + [meeting_id]
            conn.execute(
                text("DELETE FROM meeting_participants WHERE meeting_id IN :ids"),
                {"ids": tuple(all_ids)}
            )
            conn.execute(
                text("DELETE FROM meetings WHERE id IN :ids"),
                {"ids": tuple(all_ids)}
            )
            print(f"  [MySQL] 기존 데이터 삭제: meeting_id={all_ids}")

        row = conn.execute(
            text("SELECT id FROM users WHERE workspace_id = :wid LIMIT 1"),
            {"wid": workspace_id}
        ).fetchone()
        created_by = row.id if row else 1

        for pm in PAST_MEETINGS:
            conn.execute(
                text("""
                    INSERT IGNORE INTO meetings
                        (id, workspace_id, created_by, title, room_name, status, created_at, updated_at)
                    VALUES
                        (:id, :workspace_id, :created_by, :title, '테스트 룸', 'done',
                        :created_at, :created_at)
                """),
                {
                    "id": pm["meeting_id"],
                    "workspace_id": workspace_id,
                    "created_by": created_by,
                    "title": pm["title"],
                    "created_at": pm["created_at"],
                }
            )

        conn.execute(
            text("""
                INSERT IGNORE INTO meetings
                    (id, workspace_id, created_by, title, room_name, status, created_at, updated_at)
                VALUES
                    (:id, :workspace_id, :created_by, :title, '테스트 룸', 'in_progress', NOW(), NOW())
            """),
            {
                "id": meeting_id,
                "workspace_id": workspace_id,
                "created_by": created_by,
                "title": "2026-04-27 백엔드 아키텍처 논의",
            }
        )
        conn.commit()
    print(f"  [MySQL] 이전 회의 {[m['meeting_id'] for m in PAST_MEETINGS]} + 현재 회의 {meeting_id} 삽입")


def seed_redis(meeting_id: int, flush: bool):
    """Redis에 현재 회의(meeting_id 4) 발화 + 화자 + 최신 미확정 발화 삽입."""
    utterances_key = f"meeting:{meeting_id}:utterances"
    speakers_key = f"meeting:{meeting_id}:speakers"
    latest_key = f"meeting:{meeting_id}:latest"

    if flush:
        r.delete(utterances_key)
        r.delete(speakers_key)
        r.delete(latest_key)
        print(f"  [Redis] 기존 키 삭제: {utterances_key}, {speakers_key}, {latest_key}")

    for u in UTTERANCES:
        r.rpush(utterances_key, json.dumps(u, ensure_ascii=False))

    r.hset(speakers_key, mapping=SPEAKERS)

    # meeting:{id}:latest — 화자분리 없는 ASR 최신 인식 텍스트 (String)
    r.set(latest_key, LATEST_TEXT)

    r.expire(utterances_key, 86400)
    r.expire(speakers_key, 86400)
    r.expire(latest_key, 86400)

    print(f"  [Redis] 발화 {len(UTTERANCES)}건 삽입 → {utterances_key}")
    print(f"  [Redis] 화자 {len(SPEAKERS)}명 삽입 → {speakers_key}")
    print(f"  [Redis] 최신 발화 삽입 → {latest_key}")


def seed_mongo(workspace_id: int, flush: bool):
    """MongoDB meeting_contexts + utterances에 이전 회의 데이터 삽입."""
    # --- meeting_contexts (요약) ---
    ctx_col = mongo_db["meeting_contexts"]

    if flush:
        ctx_col.delete_many({})
        print("  [MongoDB] meeting_contexts 전체 삭제")

    existing_indexes = [idx["name"] for idx in ctx_col.list_indexes()]
    if "summary_text" not in existing_indexes:
        ctx_col.create_index([("summary", "text"), ("title", "text")], name="summary_text")
        print("  [MongoDB] $text 인덱스 생성: summary + title")

    for pm in PAST_MEETINGS:
        ctx_col.update_one(
            {"meeting_id": pm["meeting_id"]},
            {"$setOnInsert": {**pm, "workspace_id": workspace_id}},
            upsert=True,
        )
        print(f"  [MongoDB] 이전 회의 요약 삽입: {pm['title']}")

    # --- utterances (raw 발화, ASR 서버 스키마: 회의당 문서 1개 + nested 배열) ---
    utt_col = mongo_db["utterances"]

    if flush:
        ids = [u["meeting_id"] for u in PAST_UTTERANCES]
        utt_col.delete_many({"meeting_id": {"$in": ids}})
        print(f"  [MongoDB] utterances 기존 데이터 삭제: meeting_id={ids}")

    # utterances.text 필드 $text 검색 인덱스
    utt_indexes = [idx["name"] for idx in utt_col.list_indexes()]
    if "utterances_text" not in utt_indexes:
        utt_col.create_index(
            [("utterances.text", "text"), ("utterances.speaker_label", "text")],
            name="utterances_text"
        )
        print("  [MongoDB] utterances $text 인덱스 생성")

    for doc in PAST_UTTERANCES:
        utt_col.update_one(
            {"meeting_id": doc["meeting_id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        print(f"  [MongoDB] raw 발화 삽입: meeting_id={doc['meeting_id']} ({len(doc['utterances'])}건)")


def main():
    parser = argparse.ArgumentParser(description="더미 데이터 삽입")
    parser.add_argument("--meeting-id", default=DEFAULT_MEETING_ID, help="현재 회의 meeting_id")
    parser.add_argument("--workspace-id", type=int, default=2, help="테스트용 workspace_id")
    parser.add_argument("--flush", action="store_true", help="기존 데이터 삭제 후 재삽입")
    args = parser.parse_args()

    print(f"\n더미 데이터 삽입 시작 (현재 meeting_id={args.meeting_id}, workspace_id={args.workspace_id}, flush={args.flush})")
    seed_mysql(int(args.meeting_id), args.workspace_id, args.flush)
    seed_redis(args.meeting_id, args.flush)
    seed_mongo(args.workspace_id, args.flush)
    print(f"\n완료. /live/{args.meeting_id} 에서 ChatFAB 테스트하세요.")


if __name__ == "__main__":
    main()
