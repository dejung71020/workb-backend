# app/api/v1/deps.py
"""API v1 공통 의존성 (인증 완성 전 임시 스텁 등)."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.workspace.models import MemberRole, WorkspaceMember


def get_current_user_id() -> int:
    """임시: 로그인 완성 전까지 고정 사용자 ID 반환."""
    return 1


def require_workspace_admin(
    workspace_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> int:
    """워크스페이스 관리자만 허용."""
    row = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user_id,
        )
        .one_or_none()
    )
    if row is None or row.role != MemberRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="워크스페이스 관리자만 수행할 수 있습니다.",
        )
    return current_user_id
