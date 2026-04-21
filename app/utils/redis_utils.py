# app/utils/redis_utils.py
import redis
import json
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

mongo_db = AsyncIOMotorClient(settings.MONGODB_URL)["workb"]

r = redis.asyncio.from_url(settings.REDIS_URL)

def _resolve_speaker(speaker_id: str | None, speakers: dict, anon_map: dict) -> str:
    """
    speaker_id -> 표시 이름 변환. 화자분리 실패 케이스를 모두 처리한다.

    케이스:
        1. speaker_id가 None / 빈 문자열: STT가 화자를 아예 못 잡은 발화 -> "알 수 없음"
        2. speaker_id가 speakers 해시에 있음: 정상 케이스 -> 이름 반환
        3. speaker_id가 있지만 해시에 없음: 분리는 됐으나 미명명 화자
            -> anon_map에 순번 부여해 "화자1", "화자2" ...형태로 일관성 유지

    anon_map은 호출 측에서 발화 루프 전체에 걸쳐 공유되어야
    동일 speaker_id가 항상 같은 "화자N" 번호를 갖는다.
    """
    # 케이스 1: 화자 정보 자체가 없음
    if not speaker_id:
        return "알 수 없음"
    
    # 케이스 2: 정상 매핑
    if speaker_id in speakers:
        return speakers[speaker_id]
    
    # 케이스 3: speaker_id는 있지만 이름 미등록 -> 순번 화자명 부여
    if speaker_id not in anon_map:
        anon_map[speaker_id] = f"화자{len(anon_map) + 1}"
    return anon_map[speaker_id]

async def get_meeting_context(meeting_id: str) -> str:
    """
    전체 발화를 "[이름] 내용" 형태 문자열로 반환.
    
    화자 분리가 불안전한 발화도 "알 수 없음" / "화자N"으로 표기해
    summary_node가 내용 중심으로 처리할 수 있게 한다.
    """
    utterances_raw = await r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)
    speakers = {
        k.decode(): v.decode()
        for k, v in (await r.hgetall(f"meeting:{meeting_id}:speakers")).items()
    }
    anon_map: dict = {} # 미명명 화자 순번 공유용 - 루프 전체에서 재사용
    lines = []
    for u in utterances_raw:
        utterance = json.loads(u)
        # speaker.id 키가 없는 발화도 .get()으로 안전하게 처리
        name = _resolve_speaker(utterance.get("speaker_id"), speakers, anon_map)
        lines.append(f"[{name}] {utterance['content']}")
    return "\n".join(lines)


async def get_related_utterance(meeting_id: str, seq: int | None) -> str:
    """
    seq 기준 단일 발화 반환. vision 캡처 시점 맥락용.
    
    seq가 None이거나 범위를 벗어나면 빈 문자열 반환.
    화자분리 실패 처리는 get_meeting_context()와 동일 로직 적용.
    """
    if seq is None:
        return ""

    utterances_raw = await r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)
    if seq >= len(utterances_raw):
        return ""
    
    speakers = {
        k.decode(): v.decode()
        for k, v in (await r.hgetall(f"meeting:{meeting_id}:speakers")).items()
    }

    utterance = json.loads(utterances_raw[seq])
    # 단일 발화이므로 anon_map은 로컬 생성으로 충분
    name = _resolve_speaker(utterance.get("speaker_id"), speakers, {})
    return f"[{name}] {utterance['content']}"

async def get_past_meeting_context(meeting_id: str) -> str:
    """MongoDB meeting_contexts에서 이전 회의 컨텍스트 가져오기"""
    doc = await mongo_db["meeting_contexts"].find_one({"meeting_id": meeting_id})
    if doc:
        return doc.get("summary", "")
    return ""