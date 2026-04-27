# scripts/seed.py
from app.infra.database.session import SessionLocal
from app.domains.user.models import User
from app.domains.workspace.models import Workspace, WorkspaceMember, Department, MemberRole
from app.domains.meeting.models import Meeting, MeetingStatus
from app.domains.integration.models import Integration, ServiceType
from app.core.security import hash_password
from datetime import datetime
from pymongo import MongoClient
from app.core.config import settings

def seed_test_data():
    _seed_mysql()
    _seed_mongo()


def _seed_mysql():
    db = SessionLocal()
    try:
        if db.query(User).first():
            return

        # 1. 유저
        user = User(
            email="test@workb.com",
            hashed_password=hash_password("test1234"),
            name="테스트유저",
            role="admin",
            workspace_id=None,
        )
        db.add(user)
        db.flush()

        # 2. 워크스페이스
        workspace = Workspace(
            owner_id=user.id,
            name="테스트 워크스페이스",
            industry="IT",
            default_language="ko",
        )
        db.add(workspace)
        db.flush()
        user.workspace_id = workspace.id

        # 3. 부서 20개 삽입
        DEPARTMENT_NAMES = [
            "개발팀", "프로덕트 기획팀", "데이터 분석팀", "QA팀", "인프라/보안팀",
            "UX/UI 디자인팀", "브랜드 기획팀", "영업팀", "마케팅팀", "그로스 마케팅팀",
            "고객 성공팀", "고객 지원팀", "인사팀", "피플/컬쳐팀", "재무팀",
            "회계팀", "총무팀", "법무/컴플라이언스팀", "전략 기획팀", "경영 관리팀",
        ]
        departments = []
        for name in DEPARTMENT_NAMES:
            dept = Department(workspace_id=workspace.id, name=name)
            db.add(dept)
            departments.append(dept)
        db.flush()

        # 4. 워크스페이스 멤버 (개발팀 소속, admin)
        db.add(WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MemberRole.admin,
            department_id=departments[0].id,
        ))

        # 5. 회의 (completed 상태)
        db.add(Meeting(
            workspace_id=workspace.id,
            created_by=user.id,
            title="2025년 2분기 개발 킥오프 회의",
            status=MeetingStatus.done,
            room_name="A 회의실",
        ))

        # 6. 연동 5개 (is_connected=False)
        for service in ServiceType:
            db.add(Integration(
                workspace_id=workspace.id,
                service=service,
                is_connected=False,
            ))

        db.commit()
        print("✅ [SEED] MySQL 테스트 데이터 삽입 완료")

    except Exception as e:
        db.rollback()
        print(f"❌ [SEED] MySQL 삽입 실패: {e}")
    finally:
        db.close()


def _seed_mongo():
    try:
        print(f"[DEBUG] MONGODB_URL = {settings.MONGODB_URL}")
        # settings.MONGODB_URL만 사용 (중복 인자 제거)
        client = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
        
        # ✅ 연결/인증 테스트 강제 실행
        client.admin.command('ping')
        print("✅ [SEED] MongoDB 인증 성공!")

        db = client['meeting_assistant']
        col = db["meeting_summaries"]

        if col.find_one({"meeting_id": 1}):
            print("✅ [SEED] MongoDB 데이터 이미 존재, 스킵")
            return

        col.insert_one({
            "meeting_id": 1,
            "workspace_id": 1,
            "summary": {
                "overview": {
                    "purpose": "2025년 2분기 백엔드 개발 일정 및 역할 분담 논의",
                    "datetime_str": "2025-04-26 14:00",
                },
                "attendees": ["이대중", "김예린", "홍정우"],
                "discussion_items": [
                    {
                        "topic": "WBS 일정 확정",
                        "content": "4월 말까지 백엔드 API 완성 목표. 각자 담당 도메인 기준으로 분배.",
                    },
                    {
                        "topic": "Slack 연동 테스트",
                        "content": "Slack 내보내기 기능 구현 완료. 회의록과 보고서를 채널에 자동 전송.",
                    },
                ],
                "decisions": [
                    {
                        "decision": "보고서 포맷은 Markdown과 Excel 우선 지원",
                        "rationale": "HTML은 별도 저장 없이 즉시 변환으로 충분",
                        "opposing_opinion": "",
                    }
                ],
                "action_items": [
                    {
                        "assignee": "이대중",
                        "content": "Notion 내보내기 클라이언트 구현",
                        "deadline": "2025-05-03",
                        "priority": "high",
                        "urgency": "urgent",
                    },
                    {
                        "assignee": "김예린",
                        "content": "워크스페이스 생성 시 integration 5개 자동 INSERT 추가",
                        "deadline": "2025-05-01",
                        "priority": "normal",
                        "urgency": "normal",
                    },
                ],
                "pending_items": [],
                "next_meeting": "2025-05-03 14:00 예정",
                "previous_followups": [],
                "hallucination_flags": [],
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })

        print("✅ [SEED] MongoDB 테스트 데이터 삽입 완료")

    except Exception as e:
        print(f"❌ [SEED] MongoDB 삽입 실패: {e}")