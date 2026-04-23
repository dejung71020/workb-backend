"""
사용자 도메인의 데이터베이스 접근 로직을 담당하는 파일입니다. repository 계층은 service 계층과 데이터베이스 사이에서실제 조회 및 저장 작업을 수행합니다. 즉, service 계층은 처리 흐름을 결정하고, repository 계층은 DB에서 어떻게 조회하고 저장할지를 담당합니다.
"""

from sqlalchemy.orm import Session

from app.domains.user.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """
    이메일을 기준으로 사용자를 조회합니다.
    로그인 시 사용자를 찾거나, 회원가입 시 중복 이메일 여부를 확인할 때 사용합니다.

    Args:
        db: 데이터베이스 세션입니다.
        email: 조회할 사용자 이메일입니다.

    Returns:
        사용자가 존재하면 User 객체를 반환하고,
        존재하지 않으면 None을 반환합니다.
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """
    사용자 ID를 기준으로 사용자를 조회합니다. 토큰에 포함된 사용자 식별값으로 사용자를 다시 찾거나, 특정 사용자 정보를 조회할 때 사용할 수 있습니다.

    Args:
        db: 데이터베이스 세션입니다.
        user_id: 조회할 사용자 ID입니다.

    Returns:
        사용자가 존재하면 User 객체를 반환하고, 존재하지 않으면 None을 반환합니다.
    """
    return db.query(User).filter(User.id == user_id).first()


def get_users_by_ids(db: Session, user_ids: list[int]) -> list[User]:
    """
    사용자 ID 목록을 기준으로 사용자들을 조회합니다.

    회의 참석자 유효성 검증처럼 여러 사용자를 한 번에 확인할 때 사용합니다.
    """
    if not user_ids:
        return []

    return db.query(User).filter(User.id.in_(user_ids)).all()


def create_user(
    db: Session,
    email: str,
    hashed_password: str,
    name: str,
    role: str,
    workspace_id: int | None = None,
) -> User:
    """
    새로운 사용자를 생성하고 데이터베이스에 저장합니다. 회원가입 시 service 계층에서 전달받은 데이터를 바탕으로 User 객체를 생성하고 저장합니다.

    Args:
        db: 데이터베이스 세션입니다.
        email: 저장할 사용자 이메일입니다.
        hashed_password: 해시 처리된 비밀번호입니다.
        name: 사용자 이름입니다.
        role: 사용자 역할입니다.
        workspace_id: 연결할 워크스페이스 ID입니다.

    Returns:
        저장이 완료된 User 객체를 반환합니다.
    """
    user = User(
        email=email,
        hashed_password=hashed_password,
        name=name,
        role=role,
        workspace_id=workspace_id,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def update_user_password(
    db: Session,
    user_id: int,
    hashed_password: str,
) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    user.hashed_password = hashed_password
    db.commit()
    db.refresh(user)

    return user


def update_user_profile(
    db: Session,
    user_id: int,
    name: str,
) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    user.name = name
    db.commit()
    db.refresh(user)

    return user


def get_users_by_workspace_id(
    db: Session,
    workspace_id: int,
    department_id: int | None = None,
) -> list[User]:
    """
    워크스페이스 ID를 기준으로 해당 워크스페이스 소속 사용자 목록을 조회합니다.

    멤버 목록 조회, 권한 관리, 멤버 내보내기 기능에서 공통으로 사용할 수 있는 기본 조회 함수입니다.

    Args:
        db: 데이터베이스 세션입니다.
        workspace_id: 조회할 워크스페이스 ID입니다.
        department_id: 특정 부서 기준으로 필터링할 부서 ID입니다.

    Returns:
        해당 워크스페이스에 속한 User 객체 리스트를 반환합니다.
    """
    query = db.query(User).filter(User.workspace_id == workspace_id)

    # 부서 필터가 전달된 경우에는 해당 부서 소속 사용자만 조회합니다.
    if department_id is not None:
        query = query.filter(User.department_id == department_id)

    return query.order_by(User.id.asc()).all()


def count_users_by_department_id(db: Session, department_id: int) -> int:
    """
    특정 부서에 소속된 사용자 수를 조회합니다.

    부서 삭제 시 소속 인원이 있는지 확인하는 정책 검증에 사용합니다.

    Args:
        db: 데이터베이스 세션입니다.
        department_id: 확인할 부서 ID입니다.

    Returns:
        해당 부서에 속한 사용자 수를 반환합니다.
    """
    return db.query(User).filter(User.department_id == department_id).count()


def update_user_role(
    db: Session,
    user_id: int,
    role: str,
) -> User | None:
    """
    특정 사용자의 역할을 변경하고 저장합니다.

    권한 관리 기능에서 관리자/멤버/뷰어 역할을 변경할 때 사용합니다.

    Args:
        db: 데이터베이스 세션입니다.
        user_id: 역할을 변경할 사용자 ID입니다.
        role: 새로 저장할 역할 문자열입니다.

    Returns:
        변경된 User 객체를 반환하고, 사용자가 존재하지 않으면 None을 반환합니다.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    user.role = role
    db.commit()
    db.refresh(user)

    return user

def update_user_department(
    db: Session,
    user_id: int,
    department_id: int | None,
) -> User | None:
    """
    특정 사용자의 부서를 변경하고 저장합니다.

    부서 지정 또는 부서 해제(null) 기능에서 사용합니다.

    Args:
        db: 데이터베이스 세션입니다.
        user_id: 부서를 변경할 사용자 ID입니다.
        department_id: 새로 저장할 부서 ID입니다. 부서 해제 시 None입니다.

    Returns:
        변경된 User 객체를 반환하고, 사용자가 존재하지 않으면 None을 반환합니다.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    user.department_id = department_id
    db.commit()
    db.refresh(user)

    return user
