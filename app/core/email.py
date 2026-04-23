import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from app.core.config import settings


logger = logging.getLogger(__name__)


def _sender() -> str | None:
    if not settings.SMTP_FROM_EMAIL:
        return None
    return formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL))


def send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    """
    SMTP 설정이 있는 환경에서 메일을 발송합니다.
    설정이 없거나 발송이 실패해도 호출 흐름은 중단하지 않고 False를 반환합니다.
    """
    sender = _sender()
    if not settings.SMTP_HOST or not sender:
        logger.info("Email delivery skipped because SMTP_HOST or SMTP_FROM_EMAIL is not configured.")
        return False

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False

    return True


def send_admin_signup_welcome_email(
    to_email: str,
    name: str,
    workspace_name: str,
    invite_code: str,
) -> bool:
    if not settings.ADMIN_SIGNUP_EMAIL_ENABLED:
        return False

    login_url = f"{settings.FRONTEND_URL.rstrip('/')}/login"
    safe_name = escape(name)
    safe_workspace_name = escape(workspace_name)
    safe_invite_code = escape(invite_code)
    safe_login_url = escape(login_url, quote=True)
    subject = "Workb 관리자 가입이 완료되었습니다"
    text_body = (
        f"{name}님, Workb 관리자 가입이 완료되었습니다.\n\n"
        f"워크스페이스: {workspace_name}\n"
        f"초대코드: {invite_code}\n"
        f"로그인: {login_url}\n"
    )
    html_body = f"""
    <p>{safe_name}님, Workb 관리자 가입이 완료되었습니다.</p>
    <p><strong>워크스페이스</strong>: {safe_workspace_name}</p>
    <p><strong>초대코드</strong>: {safe_invite_code}</p>
    <p><a href="{safe_login_url}">Workb 로그인</a></p>
    """

    return send_email(to_email, subject, text_body, html_body)
