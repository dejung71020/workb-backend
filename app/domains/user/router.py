"""
사용자 도메인의 API 엔드포인트를 정의하는 파일입니다.

router 계층은 클라이언트의 요청을 직접 받고,
검증된 요청 데이터를 service 계층으로 전달하는 역할을 합니다.

현재는 인증 기능과 관련된 엔드포인트를 먼저 구성합니다.
- 관리자 회원가입
- 멤버 회원가입
- 로그인
- 비밀번호 재설정 요청
- 비밀번호 변경 요청

이제 요청 하나가 들어오면:
FastAPI가 get_db()로 DB 세션을 만듦
router.py가 그 세션을 받음
service.py에 넘김
service가 repository로 DB 작업
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.db.session import get_db
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
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserProfileUpdateResponse,
    UserResponse,
)
from app.domains.user.service import (
    change_password_service,
    confirm_password_reset_service,
    get_my_profile_service,
    login_service,
    logout_service,
    request_password_reset_service,
    refresh_token_service,
    signup_admin_service,
    signup_member_service,
    update_my_profile_service,
    withdraw_my_account_service,
)


router = APIRouter()


@router.post(
    "/signup/admin",
    response_model=AdminSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup_admin(
    payload: AdminSignupRequest,
    db: Session = Depends(get_db),
) -> AdminSignupResponse:
    """
    관리자 회원가입 요청을 처리하는 API 엔드포인트입니다.

    요청 데이터 검증은 Pydantic 스키마가 담당하고,
    실제 회원가입 처리 로직은 service 계층에 위임합니다.

    Args:
        payload: 관리자 회원가입 요청 데이터입니다.
        db: 요청에 사용되는 데이터베이스 세션입니다.

    Returns:
        회원가입 처리 결과 사용자 정보와 초대코드를 반환합니다.
    """
    return signup_admin_service(db, payload)


@router.post(
    "/signup/member",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup_member(
    payload: MemberSignupRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    멤버 회원가입 요청을 처리하는 API 엔드포인트입니다.

    Args:
        payload: 멤버 회원가입 요청 데이터입니다.
        db: 요청에 사용되는 데이터베이스 세션입니다.

    Returns:
        회원가입 처리 결과 사용자 정보를 반환합니다.
    """
    return signup_member_service(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    로그인 요청을 처리하는 API 엔드포인트입니다.

    Args:
        payload: 로그인 요청 데이터입니다.
        db: 요청에 사용되는 데이터베이스 세션입니다.

    Returns:
        로그인 처리 결과 토큰 정보를 반환합니다.
    """
    return login_service(db, payload)


@router.post(
    "/auth/token/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    refresh token으로 새 토큰을 발급하는 API 엔드포인트입니다.
    """
    return refresh_token_service(db, payload)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    로그아웃을 처리하는 API 엔드포인트입니다.
    """
    return logout_service(db, payload)


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def get_my_profile(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> UserProfileResponse:
    """
    로그인한 사용자의 마이페이지 프로필 정보를 조회합니다.
    """
    return get_my_profile_service(db, current_user_id)


@router.patch(
    "/me",
    response_model=UserProfileUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_my_profile(
    payload: UserProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> UserProfileUpdateResponse:
    """
    로그인한 사용자의 이름을 수정하고 갱신된 토큰을 발급합니다.
    """
    return update_my_profile_service(db, current_user_id, payload)


@router.delete(
    "/me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def withdraw_my_account(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> MessageResponse:
    """
    로그인한 사용자의 회원 탈퇴를 처리합니다.
    """
    return withdraw_my_account_service(db, current_user_id)


@router.post(
    "/password-reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    비밀번호 재설정 메일 발송 요청을 처리하는 API 엔드포인트입니다.

    Args:
        payload: 비밀번호 재설정 메일 발송 요청 데이터입니다.

    Returns:
        요청 처리 결과 메시지를 반환합니다.
    """
    return request_password_reset_service(db, payload)


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    비밀번호 재설정 링크에서 새 비밀번호를 저장합니다.
    """
    return confirm_password_reset_service(db, payload)


@router.post(
    "/password-change",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
) -> MessageResponse:
    """
    비밀번호 변경 요청을 처리하는 API 엔드포인트입니다.

    Args:
        payload: 비밀번호 변경 요청 데이터입니다.

    Returns:
        요청 처리 결과 메시지를 반환합니다.
    """
    return change_password_service(db, current_user_id, payload)
