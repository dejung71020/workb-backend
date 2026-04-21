"""
seed_dummy.py - /docs 테스트용 더미 데이터 삽입

삽입 대상:
    - Redis: meeting:{id}:utterances, meeting:{id}:speakers
    - MongoDB: meeting_contexts (이전 회의 요약)

화자분리 실패 케이스 포함:
    - speaker_id 없음 -> "알 수 없음"
    - speaker_id 있지만 speakers 해시에 없음 -> "화자N"

실행:
    python scripts/seed_dummy.py
    python scripts/seed_dummy.py --meeting-id test-001  # meeting_id 직접 지정
    python scripts/seed_dummy.py --flush                # 기존 데이터 삭제 후 삽입
"""
import sys, os, json, argparse
import redis
from pymongo import MongoClient
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.core.config import settings

# --- 클라이언트 ---
r = redis.from_url(settings.REDIS_URL)
mongo_db = MongoClient(settings.MONGODB_URL)["workb"]

# 테스트에 쓸 meeting_id. --meeting-id 인자로 변경 가능.
DEFAULT_MEETING_ID = "test-001"

# ------------------------------------------------------------------
# 더미 발화 데이터
# ------------------------------------------------------------------
# speaker_id 케이스를 의도적으로 세 가지로 구성:
#   1. "spk_001", "spk_002" -> speakers 해시에 이름 있음 (정상)
#   2. "spk_003"            -> speakers 해시에 없음 -> "화자3"으로 표기
#   3. None (키 없음)         -> 화자분리 완전 실패 -> "알 수 없음"으로 표기
UTTERANCES = [
    # 정상 화자
    {"speaker_id": "spk_001", "content": "오늘 회의 시작하겠습니다. 신규 백엔드 아키텍처 방향성 논의가 주요 안건입니다.", "timestamp": "2026-04-17T10:00:00"},
    {"speaker_id": "spk_002", "content": "FastAPI에서 Django로 마이그레이션하는 건 리소스 낭비인 것 같아요. 현행 유지가 낫지 않을까요?", "timestamp": "2026-04-17T10:01:00"},
    {"speaker_id": "spk_001", "content": "동의합니다. FastAPI 그대로 가되, 모듈 구조를 도메인별로 정리하는 방향으로 결정합시다.", "timestamp": "2026-04-17T10:02:00"},
    {"speaker_id": "spk_002", "content": "그러면 김철수 님이 도메인 분리 작업 맡아주실 수 있을까요? 이번 주 금요일까지 초안 부탁드립니다.", "timestamp": "2026-04-17T10:03:00"},
    {"speaker_id": "spk_001", "content": "Redis 캐시 TTL 설정 건은 아직 결론이 안 났죠? 다음 회의 전까지 검토 필요합니다.", "timestamp": "2026-04-17T10:04:00"},

    # speakers 해시에 없는 화자 (화자분리는 됐지만 이름 미등록) → "화자3"
    {"speaker_id": "spk_003", "content": "인증 모듈 리팩토링은 ASAP으로 진행해야 할 것 같습니다. 보안 이슈가 있어요.", "timestamp": "2026-04-17T10:05:00"},
    {"speaker_id": "spk_003", "content": "JWT 토큰 만료 처리 로직이 현재 누락되어 있습니다. 반드시 이번 스프린트 안에 수정해야 합니다.", "timestamp": "2026-04-17T10:06:00"},

    # speaker_id 키 자체 없음 (화자분리 완전 실패) → "알 수 없음"
    {"content": "데이터베이스 인덱스 최적화도 논의가 필요합니다.", "timestamp": "2026-04-17T10:07:00"},
    {"content": "다음 회의는 4월 24일 오전 10시로 잡겠습니다.", "timestamp": "2026-04-17T10:08:00"},

    # 다시 정상 화자
    {"speaker_id": "spk_001", "content": "이번 회의 정리하겠습니다. 도메인 분리는 김철수 님, 인증 모듈 수정은 이번 스프린트 필수, Redis TTL은 미결입니다.", "timestamp": "2026-04-17T10:09:00"},
]

# speakers 해시: spk_001, spk_002만 등록. spk_003은 의도적으로 누락.
SPEAKERS = {
    "spk_001": "박지수",
    "spk_002": "이민준",
    # spk_003 없음 → _resolve_speaker가 "화자3"으로 폴백
}

# ------------------------------------------------------------------
# MongoDB 이전 회의 요약 (follow-up 추적 테스트용)
# ------------------------------------------------------------------
# search_past_meetings()가 $text 인덱스로 검색하므로
# summary 필드에 키워드가 충분히 있어야 검색에 걸린다.
PAST_MEETING = {
    "meeting_id": "test-000",
    "title": "2026-04-10 백엔드 아키텍처 사전 논의",
    "summary": (
        "FastAPI 도메인 구조 개편 필요성에 대해 논의함. "
        "인증 모듈 JWT 토큰 만료 처리 누락 이슈 제기됨. "
        "액션 아이템: 김철수 - 도메인 분리 초안 작성 (미완료), "
        "이민준 - Redis TTL 정책 검토 (미완료)"
        "다음 회의에서 진행 상황 확인 예정. "
    ),
    "created_at": datetime(2026, 4, 10, 10, 0, 0),
}

def seed_redis(meeting_id: str, flush: bool):
    """
    Redis에 발화 리스트와 화자 해시를 삽입.

    flush=True면 기존 키를 삭제하고 새로 삽입
    flush=False면 기존 데이터에 이어 붙임 (중복 주의).
    """
    utterances_key = f"meeting:{meeting_id}:utterances"
    speakers_key = f"meeting:{meeting_id}:speakers"

    if flush:
        r.delete(utterances_key)
        r.delete(speakers_key)
        print(f" [Redis] 기존 키 삭제: {utterances_key}, {speakers_key}")

    # 발화 삽입 - PRUSH 시간 순서 유지
    for u in UTTERANCES:
        r.rpush(utterances_key, json.dumps(u, ensure_ascii=False))

    # 화자 이름 매핑 삽입
    r.hset(speakers_key, mapping=SPEAKERS)

    # TTL 24시간 설정 (운영 환경과 동일하게)
    r.expire(utterances_key, 86400)
    r.expire(speakers_key, 86400)

    print(f"  [Redis] 발화 {len(UTTERANCES)}건 삽입 → {utterances_key}")
    print(f"  [Redis] 화자 {len(SPEAKERS)}명 삽입 → {speakers_key}")
    print(f"  [Redis] 화자분리 실패 케이스: spk_003(이름 미등록), speaker_id 없음 2건")

def seed_mongo(flush: bool):
    """
    MongoDB meeting_contexts에 이전 회의 요약 삽입.

    $text 인덱스가 없으면 자동 생성.
    flush=True면 기존 test-000 문서를 삭제하고 재삽입.
    """
    col = mongo_db["meeting_contexts"]

    # $text 검색을 위한 인덱스 - 없으면 생성 (있으면 무시됨)
    existing_indexes = [idx["name"] for idx in col.list_indexes()]
    if "summary_text" not in existing_indexes:
        col.create_index([("summary", "text"), ("title", "text")], name="summary_text")
        print("  [MongoDB] $text 인덱스 생성: summary + title")
    
    if flush:
        col.delete_many({"meeting_id": PAST_MEETING["meeting_id"]})
        print(f"  [MongoDB] 기존 문서 삭제: meeting_id={PAST_MEETING['meeting_id']}")

    col.update_one(
        {"meeting_id": PAST_MEETING["meeting_id"]},
        {"$setOnInsert": PAST_MEETING},
        upsert=True, # 없으면 삽입, 있으면 skip (flush 없이 중복 방지)
    )
    print(f"  [MongoDB] 이전 회의 요약 삽입: {PAST_MEETING['title']}")

def main():
    parser = argparse.ArgumentParser(description="더미 데이터 삽입")
    parser.add_argument("--meeting-id", default=DEFAULT_MEETING_ID, help="테스트용 meeting_id")
    parser.add_argument("--flush", action="store_true", help="기존 데이터 삭제 후 재삽입")
    args = parser.parse_args()

    print(f"\n더미 데이터 삽입 시작 (meeting_id={args.meeting_id}, flush={args.flush})")
    seed_redis(args.meeting_id, args.flush)
    seed_mongo(args.flush)
    print("\n완료. /docs에서 아래로 테스트하세요:")
    print(f"  POST /api/v1/knowledge/meetings/{args.meeting_id}/chatbot/summary")
    print(f"  POST /api/v1/knowledge/meetings/{args.meeting_id}/chatbot/message")

if __name__ == "__main__":
    main()