"""
seed_dummy.py - /docs 테스트용 더미 데이터 삽입
                                                                                                                    
삽입 대상:                                                                                                           
    - Redis: meeting:{id}:utterances, meeting:{id}:speakers  (현재 회의 = meeting_id 4)                              
    - MongoDB: meeting_contexts (이전 회의 요약 = meeting_id 2, 3)                                                   
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
# ------------------------------------------------------------------                                                 
UTTERANCES = [
    {"speaker_id": "spk_001", "content": "오늘 회의 시작하겠습니다. 신규 백엔드 아키텍처 방향성 논의가 주요 안건입니다.", "timestamp": "2026-04-27T10:00:00"},                                                                   
    {"speaker_id": "spk_002", "content": "FastAPI에서 Django로 마이그레이션하는 건 리소스 낭비인 것 같아요. 현행 유지가 낫지 않을까요?", "timestamp": "2026-04-27T10:01:00"},                                                         
    {"speaker_id": "spk_001", "content": "동의합니다. FastAPI 그대로 가되, 모듈 구조를 도메인별로 정리하는 방향으로 결정합시다.", "timestamp": "2026-04-27T10:02:00"},                                                                   
    {"speaker_id": "spk_002", "content": "그러면 김철수 님이 도메인 분리 작업 맡아주실 수 있을까요? 이번 주 금요일까지 초안 부탁드립니다.", "timestamp": "2026-04-27T10:03:00"},                                                 
    {"speaker_id": "spk_001", "content": "Redis 캐시 TTL 설정 건은 아직 결론이 안 났죠? 다음 회의 전까지 검토 필요합니다.", "timestamp": "2026-04-27T10:04:00"},                                                                   
    # speakers 해시에 없는 화자 → "화자3"                                                                          
    {"speaker_id": "spk_003", "content": "인증 모듈 리팩토링은 ASAP으로 진행해야 할 것 같습니다. 보안 이슈가 있어요.", "timestamp": "2026-04-27T10:05:00"},                                                                       
    {"speaker_id": "spk_003", "content": "JWT 토큰 만료 처리 로직이 현재 누락되어 있습니다. 반드시 이번 스프린트 안에 수정해야 합니다.", "timestamp": "2026-04-27T10:06:00"},                                                             
    # speaker_id 없음 → "알 수 없음"                                                                               
    {"content": "데이터베이스 인덱스 최적화도 논의가 필요합니다.", "timestamp": "2026-04-27T10:07:00"},              
    {"content": "다음 회의는 5월 4일 오전 10시로 잡겠습니다.", "timestamp": "2026-04-27T10:08:00"},                  
    {"speaker_id": "spk_001", "content": "이번 회의 정리하겠습니다. 도메인 분리는 김철수 님, 인증 모듈 수정은 이번 스프린트 필수, Redis TTL은 미결입니다.", "timestamp": "2026-04-27T10:09:00"},                                        
]                                                                                                                    
                                                                                                                    
SPEAKERS = {                                                                                                       
    "spk_001": "박지수",
    "spk_002": "이민준",                                                                                             
    # spk_003 없음 → "화자3"으로 폴백
}                                                                                                                    
                                                                                                                    
# ------------------------------------------------------------------
# MongoDB 이전 회의 요약 (meeting_id 2, 3)
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
                                                                                                                    
def seed_mysql(meeting_id: int, workspace_id: int, flush: bool):                                                   
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:                                                                                   
        if flush:
            # 현재 회의 + 이전 회의 2개 모두 삭제                                                                    
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
                                                                                                                    
        # 이전 회의들 (done)
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
                                                                                                                    
        # 현재 회의 (in_progress)
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
                "title": f"2026-04-27 백엔드 아키텍처 논의",                                                       
            }                                                                                                        
        )
        conn.commit()                                                                                                
    print(f"  [MySQL] 이전 회의 {[m['meeting_id'] for m in PAST_MEETINGS]} + 현재 회의 {meeting_id} 삽입")         
                                                                                                                    
def seed_redis(meeting_id: int, flush: bool):
    """Redis에 현재 회의(meeting_id 4) 발화 + 화자 삽입."""                                                          
    utterances_key = f"meeting:{meeting_id}:utterances"                                                              
    speakers_key = f"meeting:{meeting_id}:speakers"
                                                                                                                    
    if flush:                                                                                                      
        r.delete(utterances_key)
        r.delete(speakers_key)
        print(f"  [Redis] 기존 키 삭제: {utterances_key}, {speakers_key}")
                                                                                                                    
    for u in UTTERANCES:
        r.rpush(utterances_key, json.dumps(u, ensure_ascii=False))                                                   
                                                                                                                    
    r.hset(speakers_key, mapping=SPEAKERS)
    r.expire(utterances_key, 86400)                                                                                  
    r.expire(speakers_key, 86400)                                                                                  
                                                                                                                    
    print(f"  [Redis] 발화 {len(UTTERANCES)}건 삽입 → {utterances_key}")
    print(f"  [Redis] 화자 {len(SPEAKERS)}명 삽입 → {speakers_key}")                                                 
                                                                                                                    
def seed_mongo(workspace_id: int, flush: bool):
    """MongoDB meeting_contexts에 이전 회의 요약 2개(meeting_id 2, 3) 삽입."""                                       
    col = mongo_db["meeting_contexts"]

    if flush:
        # 전체 삭제
        col.delete_many({})
        print(" [MongoDB] meetings_contexts 전체 삭제")                                                                              

    # $text 검색 인덱스 - 없으면 생성                                                                                
    existing_indexes = [idx["name"] for idx in col.list_indexes()]                                                 
    if "summary_text" not in existing_indexes:                                                                       
        col.create_index([("summary", "text"), ("title", "text")], name="summary_text")
        print("  [MongoDB] $text 인덱스 생성: summary + title")                                                      
                                                                                                                    
    if flush:
        ids = [m["meeting_id"] for m in PAST_MEETINGS]                                                               
        col.delete_many({"meeting_id": {"$in": ids}})                                                              
        print(f"  [MongoDB] 기존 문서 삭제: meeting_id={ids}")                                                       

    for pm in PAST_MEETINGS:                                                                                         
        col.update_one(                                                                                            
            {"meeting_id": pm["meeting_id"]},
            {"$setOnInsert": {**pm, "workspace_id": workspace_id}},                                                  
            upsert=True,  # 없으면 삽입, 있으면 skip
        )                                                                                                            
        print(f"  [MongoDB] 이전 회의 요약 삽입: {pm['title']}")                                                   
                                                                                                                    
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