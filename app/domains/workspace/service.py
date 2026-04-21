"""
워크스페이스 도메인의 비즈니스 로직을 처리하는 파일입니다.

현재는 워크스페이스 조회 기능과 초대코드 검증 기능부터 구현하며,
이후 초대코드 발급/조회 기능과 워크스페이스 설정/멤버/연동/부서 기능이 추가되면
이 파일에 비즈니스 로직을 확장해 나갑니다.
"""

import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.user.repository import (
    count_users_by_department_id,
    get_user_by_id,
    get_users_by_workspace_id,
    update_user_department,
    update_user_role,
)
from app.domains.workspace.repository import (
    create_department,
    delete_department,
    get_department_by_id,
    get_departments_by_workspace_id,
    get_workspace_by_id,
    get_workspace_by_invite_code,
    update_department,
    update_workspace,
    update_workspace_invite_code,
)

from app.domains.workspace.schemas import (
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    InviteCodeIssueResponse,
    InviteCodeValidateResponse,
    WorkspaceMemberDepartmentUpdateRequest,
    WorkspaceMemberDepartmentUpdateResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberRoleUpdateResponse,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)


def _generate_invite_code() -> str:
    """
    워크스페이스 초대코드를 생성합니다.

    현재는 대문자 기반 8자리 문자열을 사용합니다.
    워크스페이스 기능에서 초대코드를 재발급할 때 같은 규칙을 사용하기 위해
    service 계층 내부에 별도 함수로 둡니다.
    """
    return secrets.token_hex(4).upper()


def get_workspace_service(db: Session, workspace_id: int) -> WorkspaceResponse:
    """
    워크스페이스 상세 조회를 처리하는 비즈니스 로직입니다.

    처리 순서는 다음과 같습니다.
    1. workspace_id를 기준으로 워크스페이스가 존재하는지 조회합니다.
    2. 워크스페이스가 존재하는지 확인하고, 존재하지 않으면 404 Not Found 예외를 발생시킵니다.
    3. 응답 스키마 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 조회할 워크스페이스 ID입니다.

    Returns:
        조회된 워크스페이스 정보를 반환합니다.

    Raises:
        HTTPException: 워크스페이스가 존재하지 않을 경우 404 Not Found 예외를 발생시킵니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    return WorkspaceResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        invite_code=workspace.invite_code,
        industry=workspace.industry,
        default_language=workspace.default_language,
        summary_style=workspace.summary_style,
        logo_url=workspace.logo_url,
    )


def update_workspace_service(
    db: Session,
    workspace_id: int,
    payload: WorkspaceUpdateRequest,
) -> WorkspaceResponse:
    """
    워크스페이스 설정 수정을 처리합니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    updated_workspace = update_workspace(
        db=db,
        workspace_id=workspace_id,
        name=payload.name,
        industry=payload.industry,
        default_language=payload.default_language,
        summary_style=payload.summary_style,
        logo_url=payload.logo_url,
    )

    if not updated_workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    return WorkspaceResponse(
        workspace_id=updated_workspace.id,
        name=updated_workspace.name,
        invite_code=updated_workspace.invite_code,
        industry=updated_workspace.industry,
        default_language=updated_workspace.default_language,
        summary_style=updated_workspace.summary_style,
        logo_url=updated_workspace.logo_url,
    )


def validate_invite_code_service(
    db: Session,
    invite_code: str,
) -> InviteCodeValidateResponse:
    """
    초대코드 유효성 검증을 처리합니다.

    처리 순서는 다음과 같습니다.
    1. invite_code 기준으로 워크스페이스를 조회합니다.
    2. 코드가 유효한지 확인합니다.
    3. 유효하면 워크스페이스 정보를 포함해 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        invite_code: 검증할 초대코드입니다.

    Returns:
        초대코드 검증 결과와 연결된 워크스페이스 정보를 반환합니다.

    Raises:
        HTTPException: 초대코드가 유효하지 않을 경우 400 Bad Request 예외를 발생시킵니다.
    """
    workspace = get_workspace_by_invite_code(db, invite_code)

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 초대코드입니다.",
        )

    return InviteCodeValidateResponse(
        valid=True,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
    )


def get_workspace_members_service(
    db: Session,
    workspace_id: int,
    department_id: int | None = None,
) -> WorkspaceMemberListResponse:
    """
    워크스페이스 소속 멤버 목록 조회를 처리합니다.

    처리 순서는 다음과 같습니다.
    1. workspace_id 기준으로 워크스페이스가 존재하는지 확인합니다.
    2. 해당 워크스페이스 소속 사용자 목록을 조회합니다.
    3. 응답 스키마 형식으로 변환하여 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 조회할 워크스페이스 ID입니다.

    Returns:
        해당 워크스페이스 소속 멤버 목록을 반환합니다.

    Raises:
        HTTPException: 워크스페이스가 존재하지 않을 경우 404 에러를 발생시킵니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    # 부서 필터가 전달된 경우, 해당 부서가 같은 워크스페이스 소속인지 먼저 검증합니다.
    # 잘못된 department_id를 넣고도 조용히 빈 목록이 내려가는 상황을 막기 위한 처리입니다.
    if department_id is not None:
        department = get_department_by_id(db, workspace_id, department_id)
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="부서를 찾을 수 없습니다.",
            )

    users = get_users_by_workspace_id(db, workspace_id, department_id)
    departments = get_departments_by_workspace_id(db, workspace_id)

    # 사용자 응답에 부서 이름을 함께 넣기 위해 부서 ID -> 이름 매핑을 만듭니다.
    department_name_map = {
        department.id: department.name
        for department in departments
    }

    return WorkspaceMemberListResponse(
        members=[
            WorkspaceMemberResponse(
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                department_id=user.department_id,
                department=department_name_map.get(user.department_id),
            )
            for user in users
        ]
    )


def update_workspace_member_role_service(
    db: Session,
    workspace_id: int,
    user_id: int,
    role: str,
) -> WorkspaceMemberRoleUpdateResponse:
    """
    워크스페이스 소속 멤버의 역할 변경을 처리합니다.

    처리 순서는 다음과 같습니다.
    1. workspace_id 기준으로 워크스페이스가 존재하는지 확인합니다.
    2. user_id 기준으로 사용자가 존재하는지 확인합니다.
    3. 해당 사용자가 요청한 워크스페이스 소속인지 확인합니다.
    4. 역할을 변경하고 저장한 뒤 응답 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 사용자가 속한 워크스페이스 ID입니다.
        user_id: 역할을 변경할 사용자 ID입니다.
        role: 새로 저장할 역할 문자열입니다.

    Returns:
        역할이 변경된 사용자 정보를 반환합니다.

    Raises:
        HTTPException: 워크스페이스나 사용자가 존재하지 않거나, 사용자가 해당 워크스페이스 소속이 아닐 경우 예외를 발생시킵니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    if user.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="해당 워크스페이스 소속 사용자가 아닙니다.",
        )

    updated_user = update_user_role(db, user_id, role)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return WorkspaceMemberRoleUpdateResponse(
        user_id=updated_user.id,
        role=updated_user.role,
    )

def update_workspace_member_department_service(
    db: Session,
    workspace_id: int,
    user_id: int,
    payload: WorkspaceMemberDepartmentUpdateRequest,
) -> WorkspaceMemberDepartmentUpdateResponse:
    """
    워크스페이스 소속 멤버의 부서를 변경합니다.

    처리 순서는 다음과 같습니다.
    1. workspace_id 기준으로 워크스페이스가 존재하는지 확인합니다.
    2. user_id 기준으로 사용자가 존재하는지 확인합니다.
    3. 해당 사용자가 요청한 워크스페이스 소속인지 확인합니다.
    4. department_id가 전달된 경우, 해당 부서가 같은 워크스페이스 소속인지 확인합니다.
    5. 사용자 department_id를 갱신하고 응답 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 사용자가 속한 워크스페이스 ID입니다.
        user_id: 부서를 변경할 사용자 ID입니다.
        payload: 새 부서 ID 요청 데이터입니다.

    Returns:
        부서가 변경된 사용자 정보를 반환합니다.

    Raises:
        HTTPException: 워크스페이스, 사용자, 부서가 유효하지 않을 경우 예외를 발생시킵니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    if user.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="해당 워크스페이스 소속 사용자가 아닙니다.",
        )

    department_name = None

    # department_id가 None이면 부서 해제로 처리합니다.
    if payload.department_id is not None:
        department = get_department_by_id(db, workspace_id, payload.department_id)
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="부서를 찾을 수 없습니다.",
            )
        department_name = department.name

    updated_user = update_user_department(
        db=db,
        user_id=user_id,
        department_id=payload.department_id,
    )
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return WorkspaceMemberDepartmentUpdateResponse(
        user_id=updated_user.id,
        department_id=updated_user.department_id,
        department=department_name,
    )


def issue_workspace_invite_code_service(
    db: Session,
    workspace_id: int,
) -> InviteCodeIssueResponse:
    """
    워크스페이스 초대코드 발급(재발급)을 처리합니다.

    처리 순서는 다음과 같습니다.
    1. workspace_id 기준으로 워크스페이스가 존재하는지 확인합니다.
    2. 새 초대코드를 생성합니다.
    3. 워크스페이스의 기본 초대코드를 새 값으로 갱신합니다.
    4. 갱신 결과를 응답 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 초대코드를 발급할 워크스페이스 ID입니다.

    Returns:
        새로 발급된 초대코드 정보를 반환합니다.

    Raises:
        HTTPException: 워크스페이스가 존재하지 않을 경우 404 에러를 발생시킵니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    new_invite_code = _generate_invite_code()

    # 현재 구조에서는 기본 초대코드 1개만 유지하므로,
    # 새 코드를 발급하면 기존 코드를 새 값으로 덮어씁니다.
    updated_workspace = update_workspace_invite_code(
        db=db,
        workspace_id=workspace_id,
        invite_code=new_invite_code,
    )

    if not updated_workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    return InviteCodeIssueResponse(
        workspace_id=updated_workspace.id,
        invite_code=updated_workspace.invite_code,
    )


def get_workspace_departments_service(
    db: Session,
    workspace_id: int,
) -> DepartmentListResponse:
    """
    워크스페이스별 부서 목록 조회를 처리합니다.

    먼저 워크스페이스 존재 여부를 확인한 뒤,
    해당 워크스페이스 소속 부서 목록을 반환합니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    departments = get_departments_by_workspace_id(db, workspace_id)

    return DepartmentListResponse(
        departments=[
            DepartmentResponse(
                department_id=department.id,
                name=department.name,
                created_at=department.created_at,
                updated_at=department.updated_at,
            )
            for department in departments
        ]
    )


def create_workspace_department_service(
    db: Session,
    workspace_id: int,
    payload: DepartmentCreateRequest,
) -> DepartmentResponse:
    """
    워크스페이스에 새 부서를 생성합니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    department = create_department(
        db=db,
        workspace_id=workspace_id,
        name=payload.name.strip(),
    )

    return DepartmentResponse(
        department_id=department.id,
        name=department.name,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


def update_workspace_department_service(
    db: Session,
    workspace_id: int,
    department_id: int,
    payload: DepartmentUpdateRequest,
) -> DepartmentResponse:
    """
    특정 부서 이름을 수정합니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    department = get_department_by_id(db, workspace_id, department_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )

    updated_department = update_department(
        db=db,
        workspace_id=workspace_id,
        department_id=department_id,
        name=payload.name.strip(),
    )

    if not updated_department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )

    return DepartmentResponse(
        department_id=updated_department.id,
        name=updated_department.name,
        created_at=updated_department.created_at,
        updated_at=updated_department.updated_at,
    )


def delete_workspace_department_service(
    db: Session,
    workspace_id: int,
    department_id: int,
) -> None:
    """
    특정 부서를 삭제합니다.

    현재 정책은 소속 사용자가 남아 있으면 삭제를 막고 409를 반환합니다.
    """
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    department = get_department_by_id(db, workspace_id, department_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )

    member_count = count_users_by_department_id(db, department_id)
    if member_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="소속 사용자가 있는 부서는 삭제할 수 없습니다.",
        )

    deleted = delete_department(
        db=db,
        workspace_id=workspace_id,
        department_id=department_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )
