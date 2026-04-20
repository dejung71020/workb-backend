# app/api/v1/routers/workspaces.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id
from app.infra.database.session import get_db
from fastapi import Query

from app.domains.workspace.schemas import (
    DashboardResponse,
    WorkspaceListItem,
    WorkspaceListResponse,
    WorkspaceMemberItem,
    WorkspaceMembersResponse,
)
from app.domains.workspace.service import DashboardService
from app.domains.workspace.models import Workspace, WorkspaceMember
from app.domains.user.models import User

router = APIRouter()


@router.get("", response_model=WorkspaceListResponse)
def list_my_workspaces(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """현재 사용자(임시: user_id=1)가 속한 워크스페이스 목록."""
    rows = (
        db.query(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == current_user_id)
        .order_by(Workspace.id.asc())
        .all()
    )
    items = [
        WorkspaceListItem(id=int(ws.id), name=ws.name, role=str(role.value if hasattr(role, "value") else role))
        for ws, role in rows
    ]
    return WorkspaceListResponse(success=True, workspaces=items, message="OK")


@router.get("/{workspace_id}/members", response_model=WorkspaceMembersResponse)
def list_workspace_members(
    workspace_id: int,
    q: str | None = Query(None, description="이름/부서 검색어"),
    db: Session = Depends(get_db),
):
    """워크스페이스 멤버(직원) 목록."""
    query = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.id.asc())
    )
    if q is not None:
        kw = q.strip()
        if kw:
            like = f"%{kw}%"
            query = query.filter((User.name.ilike(like)) | (User.department.ilike(like)))

    rows = query.all()
    members = [
        WorkspaceMemberItem(
            user_id=int(user.id),
            name=str(user.name),
            department=getattr(user, "department", None),
            role=str(m.role.value if hasattr(m.role, "value") else m.role),
        )
        for m, user in rows
    ]
    return WorkspaceMembersResponse(success=True, members=members, message="OK")


@router.get("/{workspace_id}/dashboard", response_model=DashboardResponse)
def get_workspace_dashboard(workspace_id: int, db: Session = Depends(get_db)):
    """
    워크스페이스 홈 대시보드 데이터를 조회합니다.

    - 상태별 회의 목록 (in_progress / scheduled / done)
    - 이번 주 완료 회의 요약 (건수, 총 소요시간)
    - 미결 액션 아이템 (pending)
    - 다음 회의 제안 (추후 AI 연동 예정)
    """
    return DashboardService.get_dashboard(db, workspace_id)
