"""
사용자 도메인의 비즈니스 로직을 처리하는 파일입니다.

service 계층은 인증 기능의 전체 처리 흐름을 담당합니다.
즉, 요청을 직접 받지는 않지만,
회원가입과 로그인 시 어떤 순서로 검증하고 저장하고 응답할지 결정합니다.

현재 구현 범위는 다음과 같습니다.
- 관리자 회원가입
- 멤버 회원가입
- 로그인
- 비밀번호 재설정 요청
- 비밀번호 변경 요청

이 파일은 repository 계층을 호출하여 실제 DB 조회/저장을 수행하고,
security 계층을 호출하여 비밀번호 해시 및 토큰 발급을 처리합니다.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_admin_signup_welcome_email, send_password_reset_email
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.domains.integration.repository import create_default_integrations
from app.domains.user.repository import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_user_password,
)
from app.domains.workspace.models import MemberRole
from app.domains.workspace.repository import (
    create_workspace,
    create_workspace_membership,
    get_invite_code_by_code,
    get_workspace_by_id,
    get_workspace_by_invite_code,
    mark_invite_code_used,
)
from app.domains.user.schemas import (
    AdminSignupRequest,
    AdminSignupResponse,
    LoginRequest,
    LogoutRequest,
    MemberSignupRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
    UserRole,
)
from app.domains.user.models import User


def _generate_invite_code() -> str:
    """
    워크스페이스 초대코드를 생성합니다.

    Returns:
        대문자 기반의 8자리 초대코드를 반환합니다.
    """
    return secrets.token_hex(4).upper()


def _access_token_claims(user: User) -> dict[str, str | int | None]:
    """
    프론트가 로그인 직후 localStorage에 사용자 정보를 채울 수 있도록
    access token에 필요한 최소 프로필 정보를 함께 담습니다.
    """
    return {
        "role": user.role,
        "email": user.email,
        "name": user.name,
        "workspace_id": user.workspace_id,
    }


def signup_admin_service(db: Session, payload: AdminSignupRequest) -> AdminSignupResponse:
    """
    관리자 회원가입 요청을 처리합니다.

    처리 순서는 다음과 같습니다.
    1. 이메일 중복 여부를 확인합니다.
    2. 비밀번호를 해시 처리합니다.
    3. 관리자 역할로 사용자를 생성합니다.
    4. 저장된 사용자 정보를 응답 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        payload: 관리자 회원가입 요청 데이터입니다.

    Returns:
        저장이 완료된 관리자 사용자 응답 데이터를 반환합니다.
    """
    existing_user = get_user_by_email(db, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용 중인 이메일입니다.",
        )

    hashed_password = hash_password(payload.password)
    workspace = create_workspace(
        db=db,
        name=f"{payload.name} Workspace",
        invite_code=_generate_invite_code(),
    )

    # 워크스페이스가 생성되면 연동 관리 페이지에서 바로 상태를 조회할 수 있도록
    # 기본 integration row 5개를 함께 생성합니다.
    create_default_integrations(
        db=db,
        workspace_id=workspace.id,
    )

    user = create_user(
        db=db,
        email=payload.email,
        hashed_password=hashed_password,
        name=payload.name,
        role=UserRole.ADMIN.value,
        workspace_id=workspace.id,
    )
    create_workspace_membership(
        db=db,
        workspace_id=workspace.id,
        user_id=user.id,
        role=MemberRole.admin,
    )
    welcome_email_sent = send_admin_signup_welcome_email(
        to_email=user.email,
        name=user.name,
        workspace_name=workspace.name,
        invite_code=workspace.invite_code,
    )

    return AdminSignupResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        workspace_id=workspace.id,
        invite_code=workspace.invite_code,
        welcome_email_sent=welcome_email_sent,
    )


def signup_member_service(db: Session, payload: MemberSignupRequest) -> UserResponse:
    """
    멤버 회원가입 요청을 처리합니다.

    현재 단계에서는 초대코드의 실제 유효성 검증 없이,
    기본 회원가입 흐름만 먼저 구현합니다.

    처리 순서는 다음과 같습니다.
    1. 이메일 중복 여부를 확인합니다.
    2. 비밀번호를 해시 처리합니다.
    3. 멤버 역할로 사용자를 생성합니다.
    4. 저장된 사용자 정보를 응답 형식으로 반환합니다.

    Args:
        db: 데이터베이스 세션입니다.
        payload: 멤버 회원가입 요청 데이터입니다.

    Returns:
        저장이 완료된 멤버 사용자 응답 데이터를 반환합니다.
    """
    existing_user = get_user_by_email(db, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용 중인 이메일입니다.",
        )

    invite = get_invite_code_by_code(db, payload.invite_code)
    invite_role = MemberRole.member

    if invite:
        if invite.is_used or invite.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 초대코드입니다.",
            )
        workspace = get_workspace_by_id(db, invite.workspace_id)
        invite_role = invite.role
    else:
        workspace = get_workspace_by_invite_code(db, payload.invite_code)

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 초대코드입니다.",
        )

    hashed_password = hash_password(payload.password)

    user = create_user(
        db=db,
        email=payload.email,
        hashed_password=hashed_password,
        name=payload.name,
        role=invite_role.value,
        workspace_id=workspace.id,
    )
    create_workspace_membership(
        db=db,
        workspace_id=workspace.id,
        user_id=user.id,
        role=invite_role,
    )
    if invite:
        mark_invite_code_used(db, invite, user.id)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
    )


def login_service(db: Session, payload: LoginRequest) -> TokenResponse:
    """
    로그인 요청을 처리합니다.

    처리 순서는 다음과 같습니다.
    1. 이메일로 사용자를 조회합니다.
    2. 사용자가 존재하는지 확인합니다.
    3. 입력한 비밀번호와 저장된 해시 비밀번호를 비교합니다.
    4. 인증 성공 시 access token과 refresh token을 발급합니다.

    Args:
        db: 데이터베이스 세션입니다.
        payload: 로그인 요청 데이터입니다.

    Returns:
        발급된 토큰 응답 데이터를 반환합니다.
    """
    user = get_user_by_email(db, payload.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims=_access_token_claims(user),
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


def refresh_token_service(db: Session, payload: RefreshTokenRequest) -> TokenResponse:
    """
    refresh token을 검증하고 새 access token을 발급합니다.
    """
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        ) from None

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )

    subject = decoded.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        ) from None

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims=_access_token_claims(user),
    )
    new_refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


def logout_service(db: Session, payload: LogoutRequest) -> MessageResponse:
    """
    로그아웃 요청을 처리합니다.

    현재 구조에서는 서버 측 토큰 저장소가 없으므로,
    refresh token이 유효한 형식인지 확인한 뒤 클라이언트 폐기 메시지를 반환합니다.
    """
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        ) from None

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )

    subject = decoded.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )

    return MessageResponse(message="로그아웃되었습니다.")


def request_password_reset_service(
    db: Session,
    payload: PasswordResetRequest,
) -> MessageResponse:
    """
    비밀번호 재설정 메일 발송 요청을 처리합니다.

    사용자가 존재하면 비밀번호 재설정 링크를 이메일로 전송합니다.
    존재하지 않는 이메일이어도 계정 존재 여부가 노출되지 않도록 동일한 메시지를 반환합니다.

    Args:
        payload: 비밀번호 재설정 메일 발송 요청 데이터입니다.

    Returns:
        재설정 메일 발송 안내 메시지를 반환합니다.
    """
    user = get_user_by_email(db, payload.email)
    if user:
        token = create_access_token(
            subject=str(user.id),
            expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_MINUTES),
            extra_claims={"type": "password_reset", "email": user.email},
        )
        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        send_password_reset_email(
            to_email=user.email,
            name=user.name,
            reset_url=reset_url,
        )

    return MessageResponse(message=f"{payload.email} 주소로 비밀번호 재설정 안내를 전송했습니다.")


def confirm_password_reset_service(
    db: Session,
    payload: PasswordResetConfirmRequest,
) -> MessageResponse:
    try:
        decoded = decode_token(payload.token)
        user_id = int(decoded.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호 재설정 링크가 유효하지 않거나 만료되었습니다.",
        ) from None

    if decoded.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호 재설정 링크가 유효하지 않거나 만료되었습니다.",
        )

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    updated = update_user_password(
        db=db,
        user_id=user.id,
        hashed_password=hash_password(payload.new_password),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return MessageResponse(message="비밀번호가 성공적으로 재설정되었습니다.")


def change_password_service(
    db: Session,
    current_user_id: int,
    payload: PasswordChangeRequest,
) -> MessageResponse:
    """
    비밀번호 변경 요청을 처리합니다.

    현재 로그인한 사용자의 기존 비밀번호를 검증한 뒤 새 비밀번호로 변경합니다.

    Args:
        payload: 비밀번호 변경 요청 데이터입니다.

    Returns:
        비밀번호 변경 완료 메시지를 반환합니다.
    """
    user = get_user_by_id(db, current_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.",
        )

    updated = update_user_password(
        db=db,
        user_id=user.id,
        hashed_password=hash_password(payload.new_password),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return MessageResponse(message="비밀번호가 성공적으로 변경되었습니다.")
