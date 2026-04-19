# app\infra\clients\jira.py
import logging
import base64
from typing import Dict, Any, List
from .base import BaseClient

logger = logging.getLogger(__name__)

class JiraClient(BaseClient):
    """
    JIRA 연동
    """
    def __init__(self, domain: str, email: str, api_token: str):
        token = base64.b64encode(f"{email}:{api_token}".encdoe()).decode()
        super().__init__(
            base_url=f"https://{domain}/rest/api/3",
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            }
        )

 