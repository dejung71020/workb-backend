# app/infra/clients/notion.py
import logging
from typing import Dict, Any
from .base import BaseClient

logger = logging.getLogger(__name__)

class NotionClient(BaseClient):
    """
    Notion 연동 클라이언트.
    """
    def __init__(self, access_token: str):
        super().__init__(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28",
                "Cotent-Type": "application/json",
            }
        )