# app/core/deps.py
"""
앱 전역 FastAPI 의존성 (현재 사용자 식별 등).

워크스페이스 단위 인가(require_workspace_admin 등)는
app.domains.workspace.deps 를 사용합니다.
"""


def get_current_user_id() -> int:
    """임시: 로그인 완성 전까지 고정 사용자 ID 반환."""
    return 1
