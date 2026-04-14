# app/infra/clients/notion.py
import logging
from typing import Dict, Any
from .n8n import N8nClient

logger = logging.getLogger(__name__)

class NotionClient:
    """
    Notion 연동 클라이언트.
    직접 Notion API를 호출하지 않고 n8n 웹훅으로 함.
    """
    def __init__(self):
        self.n8n = N8nClient()

    async def export_minutes(
            self, webhook_url: str, export_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        회의록을 Notion 페이지로 내보내기 요청을 n8n에 위임

        args:
            webhook_url: integrations.extra_config['webhook_url']
            export_data: {
                "page_id": "Notion 페이지 ID",
                "title": "회의록 제목",
                "content": "회의록 전문",
                "include_wbs": true
            }
        """
        payload = {
            "action": "export_minutes",
            "data": export_data
        }
        return await self.n8n.trigger_webhook(webhook_url, payload)

    async def create_page(
            self, webhook_url: str, page_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Notion 페이지 생성 요청을 n8n에 위임

        args:
            webhook_url: integrations.extra_config['webhook_url']
            page_data: {
                "parent_id": "상위 페이지 ID",
                "title": "페이지 제목",
                "content": "페이지 내용"
            }
        """
        payload = {
            "action": "create_page",
            "data": page_data
        }
        return await self.n8n.trigger_webhook(webhook_url, payload)