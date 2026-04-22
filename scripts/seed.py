# scripts/seed.py
from app.infra.database.session import SessionLocal
from app.domains.user.models import User
from app.domains.workspace.models import Workspace, WorkspaceMember,Department, MemberRole
from app.domains.meeting.models import Meeting, MeetingStatus
from app.domains.integration.models import Integration, ServiceType

DEPARTMENT_NAMES = [
    "개발팀",
    "프로덕트 기획팀",
    "데이터 분석팀",
    "QA팀",
    "인프라/보안팀",
    "UX/UI 디자인팀",
    "브랜드 기획팀",
    "영업팀",
    "마케팅팀",
    "그로스 마케팅팀",
    "고객 성공팀",
    "고객 지원팀",
    "인사팀",
    "피플/컬쳐팀",
    "재무팀",
    "회계팀",
    "총무팀",
    "법무/컴플라이언스팀",
    "전략 기획팀",
    "경영 관리팀",
]


def seed_test_data():
    db = SessionLocal()
    try:
        if db.query(User).first():
            return

        # 1. 유저
        user = User(
            email="test@workb.com",
            hashed_password="placeholder",
            name="테스트유저",
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

        # 3. 부서 20개 삽입
        departments = []
        for name in DEPARTMENT_NAMES:
            dept = Department(workspace_id=workspace.id, name=name)
            db.add(dept)
            departments.append(dept)
        db.flush()

        # 4. 워크스페이스 멤버 (개발팀 소속)
        db.add(WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MemberRole.admin,
            department_id=departments[0].id,  # 개발팀
        ))

        # 5. 회의 (room_name 포함)
        db.add(Meeting(
            workspace_id=workspace.id,
            created_by=user.id,
            title="테스트 회의",
            status=MeetingStatus.scheduled,
            room_name="A 회의실",
        ))

        # 6. 연동 5개
        for service in ServiceType:
            db.add(Integration(
                workspace_id=workspace.id,
                service=service,
                is_connected=False,
            ))

        db.commit()
        print("🌱 [DEBUG] 테스트 데이터 삽입 완료")

    except Exception as e:
        db.rollback()
        print(f"❌ [DEBUG] 테스트 데이터 삽입 실패: {e}")
    finally:
        db.close()