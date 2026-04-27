"""
인증 도메인 테스트.

엔드포인트 prefix: /api/v1/users
- POST /signup/admin   : 관리자 회원가입
- POST /signup/member  : 멤버 회원가입 (초대코드 필요)
- POST /login          : 로그인
- POST /auth/token/refresh : 토큰 갱신
- POST /logout         : 로그아웃
- POST /password-reset : 비밀번호 재설정 요청
- POST /password-change : 비밀번호 변경
"""

import pytest
from app.core.security import create_refresh_token


BASE = "/api/v1/users"


# ---------------------------------------------------------------------------
# 관리자 회원가입
# ---------------------------------------------------------------------------

class TestAdminSignup:
    def test_success(self, client):
        res = client.post(f"{BASE}/signup/admin", json={
            "email": "admin@example.com",
            "password": "Secret123",
            "name": "홍길동",
        })
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == "admin@example.com"
        assert body["role"] == "admin"
        assert "workspace_id" in body
        assert "invite_code" in body

    def test_duplicate_email_returns_400(self, client):
        payload = {"email": "dup@example.com", "password": "Secret123", "name": "중복이"}
        client.post(f"{BASE}/signup/admin", json=payload)
        res = client.post(f"{BASE}/signup/admin", json=payload)
        assert res.status_code == 400

    def test_password_too_short_returns_422(self, client):
        res = client.post(f"{BASE}/signup/admin", json={
            "email": "short@example.com",
            "password": "Sh1",
            "name": "짧은비번",
        })
        assert res.status_code == 422

    def test_password_no_number_returns_422(self, client):
        res = client.post(f"{BASE}/signup/admin", json={
            "email": "nonumber@example.com",
            "password": "NoNumber",
            "name": "숫자없음",
        })
        assert res.status_code == 422

    def test_password_no_letter_returns_422(self, client):
        res = client.post(f"{BASE}/signup/admin", json={
            "email": "noletter@example.com",
            "password": "12345678",
            "name": "문자없음",
        })
        assert res.status_code == 422

    def test_invalid_email_returns_422(self, client):
        res = client.post(f"{BASE}/signup/admin", json={
            "email": "not-an-email",
            "password": "Secret123",
            "name": "이메일오류",
        })
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# 멤버 회원가입
# ---------------------------------------------------------------------------

class TestMemberSignup:
    def test_success(self, client, workspace):
        res = client.post(f"{BASE}/signup/member", json={
            "invite_code": workspace.invite_code,
            "email": "member@example.com",
            "password": "Member123",
            "name": "멤버이름",
        })
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == "member@example.com"
        assert body["role"] == "member"

    def test_invite_code_normalized_to_uppercase(self, client, workspace):
        """초대코드는 소문자로 입력해도 대문자로 정규화됩니다."""
        res = client.post(f"{BASE}/signup/member", json={
            "invite_code": workspace.invite_code.lower(),
            "email": "lower@example.com",
            "password": "Lower123",
            "name": "소문자코드",
        })
        assert res.status_code == 201

    def test_invalid_invite_code_returns_400(self, client):
        res = client.post(f"{BASE}/signup/member", json={
            "invite_code": "BADCODE",
            "email": "bad@example.com",
            "password": "Member123",
            "name": "잘못된코드",
        })
        assert res.status_code == 400

    def test_duplicate_email_returns_400(self, client, workspace):
        payload = {
            "invite_code": workspace.invite_code,
            "email": "dup@example.com",
            "password": "Member123",
            "name": "중복멤버",
        }
        client.post(f"{BASE}/signup/member", json=payload)
        res = client.post(f"{BASE}/signup/member", json=payload)
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------

class TestLogin:
    def _signup_admin(self, client):
        client.post(f"{BASE}/signup/admin", json={
            "email": "login@example.com",
            "password": "Login123",
            "name": "로그인테스트",
        })

    def test_success(self, client):
        self._signup_admin(client)
        res = client.post(f"{BASE}/login", json={
            "email": "login@example.com",
            "password": "Login123",
        })
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_wrong_email_returns_401(self, client):
        res = client.post(f"{BASE}/login", json={
            "email": "nobody@example.com",
            "password": "Login123",
        })
        assert res.status_code == 401

    def test_wrong_password_returns_401(self, client):
        self._signup_admin(client)
        res = client.post(f"{BASE}/login", json={
            "email": "login@example.com",
            "password": "WrongPw1",
        })
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# 토큰 갱신
# ---------------------------------------------------------------------------

class TestRefreshToken:
    def test_success(self, client, admin_user):
        user, _ = admin_user
        refresh = create_refresh_token(subject=str(user.id))
        res = client.post(f"{BASE}/auth/token/refresh", json={"refresh_token": refresh})
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_invalid_token_returns_401(self, client):
        res = client.post(f"{BASE}/auth/token/refresh", json={"refresh_token": "bad.token.here"})
        assert res.status_code == 401

    def test_access_token_as_refresh_returns_401(self, client, admin_token):
        """access token을 refresh token으로 사용하면 거부됩니다."""
        res = client.post(f"{BASE}/auth/token/refresh", json={"refresh_token": admin_token})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# 로그아웃
# ---------------------------------------------------------------------------

class TestLogout:
    def test_success(self, client, admin_user):
        user, _ = admin_user
        refresh = create_refresh_token(subject=str(user.id))
        res = client.post(f"{BASE}/logout", json={"refresh_token": refresh})
        assert res.status_code == 200
        assert "message" in res.json()

    def test_invalid_token_returns_401(self, client):
        res = client.post(f"{BASE}/logout", json={"refresh_token": "invalid.token"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# 비밀번호 재설정 / 변경
# ---------------------------------------------------------------------------

class TestPasswordReset:
    def test_reset_request_success(self, client):
        res = client.post(f"{BASE}/password-reset", json={"email": "any@example.com"})
        assert res.status_code == 200
        assert "message" in res.json()

    def test_password_change_success(self, client):
        res = client.post(f"{BASE}/password-change", json={
            "token": "some-reset-token",
            "new_password": "NewPass123",
        })
        assert res.status_code == 200
        assert "message" in res.json()

    def test_password_change_weak_password_returns_422(self, client):
        res = client.post(f"{BASE}/password-change", json={
            "token": "token",
            "new_password": "12345678",  # 숫자만
        })
        assert res.status_code == 422
