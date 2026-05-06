from app.infra.database.session import SessionLocal
from app.core.ontology.schema import EntityType, RelationType, Relation
from datetime import date

# ──────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────────


def _parse_date(val) -> date | None:
    """ctx에서 꺼낸 날짜값을 date 객체로 변환. 이미 date면 그대로."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val))
    except Exception:
        return None


# ──────────────────────────────────────────────
# 단건 엔티티 fetch 함수
# 시그니처: (entity_id, workspace_id, ctx=None) → list[dict]
# - entity_id: 출발 엔티티의 PK
# - workspace_id: 접근 범위 제한용 (다른 워크스페이스 데이터 노출 방지)
# - ctx : {"date_from": date, "date_to": date} 날짜 필터
# ──────────────────────────────────────────────
def fetch_user_meetings(
    user_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """User → 참여한 Meeting 목록 (최근 10개, 날짜 필터 가능)"""
    from app.domains.meeting.models import Meeting, MeetingParticipant

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = (
            db.query(Meeting.id, Meeting.title, Meeting.scheduled_at, Meeting.status)
            .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
            .filter(
                MeetingParticipant.user_id == user_id,
                Meeting.workspace_id == workspace_id,
            )
        )
        if date_from:
            q = q.filter(Meeting.scheduled_at >= date_from)
        if date_to:
            q = q.filter(Meeting.scheduled_at <= date_to)
        rows = q.order_by(Meeting.scheduled_at.desc()).limit(10).all()

        return [
            {
                "id": r.id,
                "type": EntityType.MEETING.value,
                "title": r.title,
                "date": r.scheduled_at.strftime("%Y-%m-%d") if r.scheduled_at else None,
                "status": r.status.value if r.status else None,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_user_tasks(
    user_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """User → 담당한 WbsTask 목록 (날짜 필터: due_date 기준)"""
    from app.domains.action.models import WbsTask
    from app.domains.meeting.models import Meeting

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = (
            db.query(WbsTask)
            .join(Meeting, WbsTask.meeting_id == Meeting.id)
            .filter(
                WbsTask.assignee_id == user_id, Meeting.workspace_id == workspace_id
            )
        )
        if date_from:
            q = q.filter(WbsTask.due_date >= date_from)
        if date_to:
            q = q.filter(WbsTask.due_date <= date_to)
        rows = q.order_by(WbsTask.due_date.desc()).limit(10).all()

        return [
            {
                "id": r.id,
                "type": EntityType.WBS_TASK.value,
                "title": r.title,
                "status": r.status.value if r.status else None,
                "progress": r.progress,
                "due_date": r.due_date.strftime("%Y-%m-%d") if r.due_date else None,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_user_department(
    user_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """User → 소속 Department"""
    from app.domains.workspace.models import WorkspaceMember, Department

    db = SessionLocal()
    try:
        row = (
            db.query(Department.id, Department.name)
            .join(WorkspaceMember, Department.id == WorkspaceMember.department_id)
            .filter(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
            .first()
        )
        if not row:
            return []
        return [{"id": row.id, "type": EntityType.DEPARTMENT.value, "name": row.name}]
    except Exception:
        return []
    finally:
        db.close()


def fetch_meeting_decisions(
    meeting_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """Meeting → Decision 목록 (날짜 필터: detected_at 기준)"""
    from app.domains.intelligence.models import Decision

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = db.query(Decision).filter(Decision.meeting_id == meeting_id)
        if date_from:
            q = q.filter(Decision.detected_at >= date_from)
        if date_to:
            q = q.filter(Decision.detected_at <= date_to)
        rows = q.order_by(Decision.detected_at.asc()).all()
        return [
            {
                "id": r.id,
                "type": EntityType.DECISION.value,
                "content": r.content,
                "is_confirmed": r.is_confirmed,
                "detected_at": (
                    r.detected_at.strftime("%Y-%m-%d") if r.detected_at else None
                ),
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_meeting_tasks(
    meeting_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """Meeting → WbsTask 목록"""
    from app.domains.action.models import WbsTask

    db = SessionLocal()
    try:
        rows = (
            db.query(WbsTask)
            .filter(WbsTask.meeting_id == meeting_id)
            .order_by(WbsTask.due_date.asc())
            .all()
        )
        return [
            {
                "id": r.id,
                "type": EntityType.WBS_TASK.value,
                "title": r.title,
                "status": r.status.value if r.status else None,
                "progress": r.progress,
                "due_date": r.due_date.strftime("%Y-%m-%d") if r.due_date else None,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_meeting_members(
    meeting_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """Meeting → 참석자 User 목록"""
    from app.domains.meeting.models import MeetingParticipant
    from app.domains.user.models import User

    db = SessionLocal()

    try:
        rows = (
            db.query(User.id, User.name, MeetingParticipant.is_host)
            .join(MeetingParticipant, User.id == MeetingParticipant.user_id)
            .filter(MeetingParticipant.meeting_id == meeting_id)
            .order_by(MeetingParticipant.is_host.desc(), User.name.asc())
            .all()
        )

        return [
            {
                "id": r.id,
                "type": EntityType.USER.value,
                "name": r.name,
                "is_host": r.is_host,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_meeting_reports(
    meeting_id: int, workspace_id: int, ctx: dict | None = None
) -> list[dict]:
    """Meeting → Report 목록"""
    from app.domains.intelligence.models import MeetingMinute

    db = SessionLocal()

    try:
        rows = (
            db.query(MeetingMinute).filter(MeetingMinute.meeting_id == meeting_id).all()
        )
        return [
            {
                "id": r.id,
                "type": EntityType.REPORT.value,
                "status": r.status.value if r.status else None,
                "review_status": r.review_status,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────
# 워크스페이스 집합 fetch 함수
# entity_id 자리에 workspace_id 가 들어온다
# ──────────────────────────────────────────────────────────────────


def fetch_ws_members(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 전체 멤버 목록"""
    from app.domains.workspace.models import WorkspaceMember
    from app.domains.user.models import User

    db = SessionLocal()
    try:
        rows = (
            db.query(User.id, User.name, User.email, WorkspaceMember.role)
            .join(WorkspaceMember, User.id == WorkspaceMember.user_id)
            .filter(WorkspaceMember.workspace_id == workspace_id)
            .all()
        )
        return [
            {
                "id": r.id,
                "type": EntityType.USER.value,
                "name": r.name,
                "email": r.email,
                "role": r.role.value if r.role else None,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_departments(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 전체 부서 목록"""
    from app.domains.workspace.models import Department

    db = SessionLocal()
    try:
        rows = (
            db.query(Department).filter(Department.workspace_id == workspace_id).all()
        )
        return [
            {"id": r.id, "type": EntityType.DEPARTMENT.value, "name": r.name}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_reports(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 전체 보고서 (날짜 필터: 회의 scheduled_at 기준)"""
    from app.domains.intelligence.models import MeetingMinute
    from app.domains.meeting.models import Meeting

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = (
            db.query(MeetingMinute, Meeting.title, Meeting.scheduled_at)
            .join(Meeting, MeetingMinute.meeting_id == Meeting.id)
            .filter(Meeting.workspace_id == workspace_id)
        )
        if date_from:
            q = q.filter(Meeting.scheduled_at >= date_from)
        if date_to:
            q = q.filter(Meeting.scheduled_at <= date_to)
        rows = q.order_by(Meeting.scheduled_at.desc()).limit(20).all()
        return [
            {
                "id": minute.id,
                "type": EntityType.REPORT.value,
                "meeting_title": title,
                "date": scheduled_at.strftime("%Y-%m-%d") if scheduled_at else None,
                "status": minute.status.value if minute.status else None,
            }
            for minute, title, scheduled_at in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_schedule(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 예정 회의 일정 (날짜 필터 가능, 기본: 미래 회의)"""
    from app.domains.meeting.models import Meeting, MeetingStatus
    from datetime import datetime

    date_from = _parse_date((ctx or {}).get("date_from")) or datetime.date()
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = db.query(
            Meeting.id, Meeting.title, Meeting.scheduled_at, Meeting.status
        ).filter(
            Meeting.workspace_id == workspace_id,
            Meeting.status == MeetingStatus.scheduled,
            Meeting.scheduled_at >= date_from,
        )
        if date_to:
            q = q.filter(Meeting.scheduled_at <= date_to)
        rows = q.order_by(Meeting.scheduled_at.asc()).limit(10).all()
        return [
            {
                "id": r.id,
                "type": EntityType.MEETING.value,
                "title": r.title,
                "date": (
                    r.scheduled_at.strftime("%Y-%m-%d %H:%M")
                    if r.scheduled_at
                    else None
                ),
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_device(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 장비/환경 설정"""
    from app.domains.workspace.models import WorkspaceDeviceSetting

    db = SessionLocal()
    try:
        rows = (
            db.query(WorkspaceDeviceSetting)
            .filter(WorkspaceDeviceSetting.workspace_id == workspace_id)
            .all()
        )
        return [
            {
                "id": r.id,
                "type": EntityType.WS_DEVICE.value,
                "device_name": r.device_name,
                "mic_enabled": r.mic_enabled,
                "camera_enabled": r.camera_enabled,
                "speaker_enabled": r.speaker_enabled,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_integration(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 외부 서비스 연동 상태"""
    from app.domains.integration.models import IntegrationSetting

    db = SessionLocal()
    try:
        rows = (
            db.query(IntegrationSetting)
            .filter(IntegrationSetting.workspace_id == workspace_id)
            .all()
        )
        return [
            {
                "id": r.id,
                "type": EntityType.WS_INTEGRATION.value,
                "service": r.service_name,
                "is_connected": r.is_connected,
                "token_expire_at": (
                    r.token_expire_at.isoformat() if r.token_expire_at else None
                ),
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_tasks(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 전체 WBS 태스크 (날짜 필터: due_date 기준)"""
    from app.domains.action.models import WbsTask
    from app.domains.meeting.models import Meeting

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = (
            db.query(WbsTask)
            .join(Meeting, WbsTask.meeting_id == Meeting.id)
            .filter(Meeting.workspace_id == workspace_id)
        )
        if date_from:
            q = q.filter(WbsTask.due_date >= date_from)
        if date_to:
            q = q.filter(WbsTask.due_date <= date_to)
        rows = q.order_by(WbsTask.due_date.asc()).limit(20).all()
        return [
            {
                "id": r.id,
                "type": EntityType.WBS_TASK.value,
                "title": r.title,
                "status": r.status.value if r.status else None,
                "progress": r.progress,
                "due_date": r.due_date.strftime("%Y-%m-%d") if r.due_date else None,
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


def fetch_ws_decisions(
    workspace_id: int, _ws_id: int, ctx: dict | None = None
) -> list[dict]:
    """워크스페이스 전체 결정 사항 (날짜 필터: detected_at 기준)"""
    from app.domains.intelligence.models import Decision
    from app.domains.meeting.models import Meeting

    date_from = _parse_date((ctx or {}).get("date_from"))
    date_to = _parse_date((ctx or {}).get("date_to"))

    db = SessionLocal()
    try:
        q = (
            db.query(Decision, Meeting.title)
            .join(Meeting, Decision.meeting_id == Meeting.id)
            .filter(Meeting.workspace_id == workspace_id)
        )
        if date_from:
            q = q.filter(Decision.detected_at >= date_from)
        if date_to:
            q = q.filter(Decision.detected_at <= date_to)
        rows = q.order_by(Decision.detected_at.desc()).limit(20).all()
        return [
            {
                "id": decision.id,
                "type": EntityType.DECISION.value,
                "content": decision.content,
                "is_confirmed": decision.is_confirmed,
                "meeting_title": title,
                "detected_at": (
                    decision.detected_at.strftime("%Y-%m-%d")
                    if decision.detected_at
                    else None
                ),
            }
            for decision, title in rows
        ]
    except Exception:
        return []
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────
# ONTOLOGY 레지스트리
#
# 온톨로지의 "공리(Axiom)" 목록.
# 각 Relation이 "어떤 엔티티에서 어떤 엔티티로 어떻게 이동하는가"를
# 선언적으로 정의한다. traverser는 이 목록을 참조해 탐색 경로를 결정한다.
#
# weight 가이드:
#   2.0 = 질문 의도와 직결될 확률이 높은 핵심 관계 (결정사항, 태스크)
#   1.8 = 중요도 높은 관계 (할당된 태스크)
#   1.5 = 보통 이상 (보고서, 참여 회의, 부서)
#   1.2 = 맥락용 (참석자, 일반 관계)
#   1.0 = 기본값 (워크스페이스 집합 조회)
# ──────────────────────────────────────────────────────────────────
ONTOLOGY: list[Relation] = [
    # User 기점 관계
    Relation(
        type=RelationType.PARTICIPATED_IN,
        from_entity=EntityType.USER,
        to_entity=EntityType.MEETING,
        fetch_fn=fetch_user_meetings,
        description="사용자가 참여한 회의",
        infer_at_depth=1,
        weight=1.5,
    ),
    Relation(
        type=RelationType.ASSIGNED_TO,
        from_entity=EntityType.USER,
        to_entity=EntityType.WBS_TASK,
        fetch_fn=fetch_user_tasks,
        description="사용자에게 할당된 태스크",
        infer_at_depth=1,
        weight=1.8,
    ),
    Relation(
        type=RelationType.BELONGS_TO,
        from_entity=EntityType.USER,
        to_entity=EntityType.DEPARTMENT,
        fetch_fn=fetch_user_department,
        description="사용자의 소속 부서",
        infer_at_depth=1,
        weight=1.0,
    ),
    # Meeting 기점 관계
    # infer_at_depth=2: User→Meeting을 거친 후에만 로드 (root에서 직접 fetch 시 건너뜀)
    # → "박민준의 회의" 컨텍스트 아래에서만 결정사항/태스크를 프리패치
    Relation(
        type=RelationType.HAS_DECISION,
        from_entity=EntityType.MEETING,
        to_entity=EntityType.DECISION,
        fetch_fn=fetch_meeting_decisions,
        description="회의에서 나온 결정 사항",
        infer_at_depth=2,
        weight=2.0,  # 가장 높은 우선순위 — 결정사항은 핵심 정보
    ),
    Relation(
        type=RelationType.HAS_TASK,
        from_entity=EntityType.MEETING,
        to_entity=EntityType.WBS_TASK,
        fetch_fn=fetch_meeting_tasks,
        description="회의에서 생성된 WBS 태스크",
        infer_at_depth=2,
        weight=1.8,
    ),
    Relation(
        type=RelationType.HAS_REPORT,
        from_entity=EntityType.MEETING,
        to_entity=EntityType.REPORT,
        fetch_fn=fetch_meeting_reports,
        description="회의 보고서",
        infer_at_depth=2,
        weight=1.5,
    ),
    Relation(
        type=RelationType.HAS_MEMBER,
        from_entity=EntityType.MEETING,
        to_entity=EntityType.USER,
        fetch_fn=fetch_meeting_members,
        description="회의 참석자",
        infer_at_depth=2,
        weight=1.2,
    ),
    # 워크스페이스 집합 관계 (WS_* 엔티티 → 목록 반환)
    Relation(
        type=RelationType.LISTS_MEMBERS,
        from_entity=EntityType.WS_MEMBERS,
        to_entity=EntityType.USER,
        fetch_fn=fetch_ws_members,
        description="워크스페이스 전체 멤버",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_DEPARTMENTS,
        from_entity=EntityType.WS_DEPARTMENTS,
        to_entity=EntityType.DEPARTMENT,
        fetch_fn=fetch_ws_departments,
        description="워크스페이스 전체 부서",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_REPORTS,
        from_entity=EntityType.WS_REPORTS,
        to_entity=EntityType.REPORT,
        fetch_fn=fetch_ws_reports,
        description="워크스페이스 전체 보고서",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_SCHEDULE,
        from_entity=EntityType.WS_SCHEDULE,
        to_entity=EntityType.MEETING,
        fetch_fn=fetch_ws_schedule,
        description="예정된 회의 일정",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_DEVICE,
        from_entity=EntityType.WS_DEVICE,
        to_entity=EntityType.WS_DEVICE,
        fetch_fn=fetch_ws_device,
        description="장비/환경 설정",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_INTEGRATION,
        from_entity=EntityType.WS_INTEGRATION,
        to_entity=EntityType.WS_INTEGRATION,
        fetch_fn=fetch_ws_integration,
        description="외부 서비스 연동 상태",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_TASKS,
        from_entity=EntityType.WS_TASKS,
        to_entity=EntityType.WBS_TASK,
        fetch_fn=fetch_ws_tasks,
        description="워크스페이스 전체 WBS 태스크",
        infer_at_depth=1,
        weight=1.0,
    ),
    Relation(
        type=RelationType.LISTS_DECISIONS,
        from_entity=EntityType.WS_DECISIONS,
        to_entity=EntityType.DECISION,
        fetch_fn=fetch_ws_decisions,
        description="워크스페이스 전체 결정 사항",
        infer_at_depth=1,
        weight=1.0,
    ),
]
