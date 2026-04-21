"""
외부 연동(integration) 도메인의 데이터베이스 접근 로직입니다.

워크스페이스 생성 직후 기본 연동 row를 보강하는 기능과
OAuth/API Key 방식의 실제 연동 저장 기능을 함께 제공합니다.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.domains.integration.models import Integration, ServiceType


DEFAULT_INTEGRATION_SERVICES = [
    ServiceType.jira,
    ServiceType.slack,
    ServiceType.notion,
    ServiceType.google_calendar,
    ServiceType.kakao,
]


def _normalize_service(service: ServiceType | str) -> ServiceType:
    if isinstance(service, ServiceType):
        return service
    return ServiceType(service.replace("-", "_"))


def create_default_integrations(db: Session, workspace_id: int) -> list[Integration]:
    return ensure_default_integrations(db, workspace_id)


def ensure_default_integrations(db: Session, workspace_id: int) -> list[Integration]:
    existing_integrations = get_integrations(db, workspace_id)
    existing_services = {
        _normalize_service(integration.service)
        for integration in existing_integrations
    }

    missing_services = [
        service
        for service in DEFAULT_INTEGRATION_SERVICES
        if service not in existing_services
    ]

    if missing_services:
        db.add_all([
            Integration(
                workspace_id=workspace_id,
                service=service,
                is_connected=False,
            )
            for service in missing_services
        ])
        db.commit()

    return get_integrations(db, workspace_id)


def get_integrations(db: Session, workspace_id: int) -> list[Integration]:
    return (
        db.query(Integration)
        .filter(Integration.workspace_id == workspace_id)
        .order_by(Integration.id.asc())
        .all()
    )


def get_integrations_by_workspace_id(db: Session, workspace_id: int) -> list[Integration]:
    return get_integrations(db, workspace_id)


def get_integration(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
) -> Optional[Integration]:
    normalized_service = _normalize_service(service)
    return (
        db.query(Integration)
        .filter(
            Integration.workspace_id == workspace_id,
            Integration.service == normalized_service,
        )
        .first()
    )


def get_integration_by_service(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
) -> Optional[Integration]:
    return get_integration(db, workspace_id, service)


def upsert_integration(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
    webhook_url: str,
) -> Integration:
    normalized_service = _normalize_service(service)
    integration = get_integration(db, workspace_id, normalized_service)

    if integration:
        integration.extra_config = {"webhook_url": webhook_url}
        integration.is_connected = True
    else:
        integration = Integration(
            workspace_id=workspace_id,
            service=normalized_service,
            extra_config={"webhook_url": webhook_url},
            is_connected=True,
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)
    return integration


def disconnect_integration(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
) -> Optional[Integration]:
    integration = get_integration(db, workspace_id, service)

    if integration:
        integration.extra_config = None
        integration.is_connected = False
        integration.access_token = None
        integration.refresh_token = None
        integration.token_expires_at = None
        db.commit()
        db.refresh(integration)

    return integration


def update_integration_connection(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
    is_connected: bool,
) -> Optional[Integration]:
    normalized_service = _normalize_service(service)
    integration = get_integration(db, workspace_id, normalized_service)
    if not integration:
        return None

    integration.is_connected = is_connected
    if not is_connected:
        integration.extra_config = None
        integration.access_token = None
        integration.refresh_token = None
        integration.token_expires_at = None

    db.commit()
    db.refresh(integration)
    return integration


def update_tokens(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
    access_token: str,
    refresh_token: Optional[str] = None,
    token_expires_at: Optional[datetime] = None,
    extra_config: Optional[dict] = None,
) -> Integration:
    normalized_service = _normalize_service(service)
    integration = get_integration(db, workspace_id, normalized_service)
    if not integration:
        integration = Integration(
            workspace_id=workspace_id,
            service=normalized_service,
        )
        db.add(integration)

    integration.access_token = access_token
    integration.refresh_token = refresh_token
    integration.token_expires_at = token_expires_at
    integration.is_connected = True
    if extra_config:
        integration.extra_config = extra_config

    db.commit()
    db.refresh(integration)
    return integration
