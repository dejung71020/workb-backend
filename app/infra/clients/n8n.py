# app/infra/clinets/n8n.py
import uuid
import logging
from typing import Dict, Any
from .session_manager import ClientSessionManager
from app.core.config import settings

logger = logging.getLogger(__name__)

class N8nClient:
    """
    n8n 웹훅을 호출하는 클라이언트.
    JIRA, Notion, Google calandar, kakao

    ClientSessionManager   →   "HTTP 통신 도구"
      httpx.AsyncClient       get/post/put 등 실제 요청을 보내는 객체

    trigger_webhook        →   "n8n과 소통하는 창구"
        webhook_url + payload       무엇을 어디로 보낼지
        response                    n8n이 뭘 처리했는지 결과

    N8nClient              →   "외부 서비스들의 공통 허브"
        JIRA, Notion, Google,       얘네가 직접 API 연결 없이
        카카오 모두 여기를 통해      n8n에 맡기는 구조
    """
    async def trigger_webhook(
            self, webhook_url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        n8n 웹 훅 URL에 POST 요청을 보냄

        args:
            webhook_url : integrations.extra_config['webhook_url'] 에서 꺼낸 전체 URL
            payload: n8n 워크플로우에 전달한 JSON

            await n8n.trigger_webhook(
            webhook_url = "http://localhost:5678/webhook/jira-1",
            payload = {
                "action": "create_issues_bulk",
                "data": {
                    "issues": [
                        {
                            "summary": "로그인 API 개발",
                            "description": "JWT 기반 로그인 구현",
                            "issue_type": "Task",
                            "priority": "High",
                            "assignee": "dev@company.com"
                        },
                        {
                            "summary": "회원가입 API 개발",
                            "description": "이메일 인증 포함",
                            "issue_type": "Task",
                            "priority": "Medium",
                            "assignee": "dev2@company.com"
                        }
                    ]
                }
            }
        )

        Returns:
            n8n 워크플로우 실행 결과 JSON
            {
                "status": "success",
                "created": [
                    {
                        "summary": "로그인 API 개발",
                        "jira_issue_id": "PROJ-101",
                        "issue_url": "https://company.atlassian.net/browse/PROJ-101"
                    },
                    {
                        "summary": "회원가입 API 개발",
                        "jira_issue_id": "PROJ-102",
                        "issue_url": "https://company.atlassian.net/browse/PROJ-102"
                    }
                ],
                "failed": []
            }
        """
        client = await ClientSessionManager.get_client()

        try:
            response = await client.post(webhook_url, json=payload)
            """
            response = {
                "executionId": "abc123",
                "status": "success"
            }
            """

            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            logger.error(f"n8n 웹훅 에러 : {str(e)}")
            raise e
        
    def _api_headers(self) -> Dict[str, str]:
        return {
            "X-N8N-API-KEY": settings.N8N_API_KEY or "",
            "Content-Type": "application/json",
        }

    def _build_workflow(self, name: str, path: str) -> Dict[str, Any]:
        """Webhook 단일 노드 — 수신 즉시 200 응답"""
        return {
            "name": name,
            "nodes": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 2,
                    "position": [250, 300],
                    "parameters": {
                        "httpMethod": "POST",
                        "path": path,
                        "responseMode": "onReceived",
                        "options": {},
                    },
                    "webhookId": str(uuid.uuid4()),
                },
            ],
            "connections": {},
            "settings": {"executionOrder": "v1"},
            "staticData": None,
        }

    async def create_and_activate_workflow(self, name: str, path: str) -> str:
        """
        워크플로우 생성 후 활성화.
        이미 존재하면 스킵 (idempotent).
        Returns: workflow_id
        """
        client = await ClientSessionManager.get_client()
        headers = self._api_headers()
        base = settings.N8N_BASE_URL.rstrip("/")

        # 기존 워크플로우 확인
        res = await client.get(f"{base}/api/v1/workflows", headers=headers)
        res.raise_for_status()
        for wf in res.json().get("data", []):
            if wf.get("name") == name:
                logger.info(f"워크플로우 이미 존재, 스킵: {name}")
                if not wf.get("active"):
                    await client.post(
                        f"{base}/api/v1/workflows/{wf['id']}/activate",
                        headers=headers
                    )
                return wf["id"]

        # 생성
        body = self._build_workflow(name, path)
        res = await client.post(f"{base}/api/v1/workflows", json=body, headers=headers)
        if res.status_code >= 400:
            logger.error(f"n8n 응답 상세: {res.text}")
        res.raise_for_status()
        workflow_id = res.json()["id"]
        logger.info(f"워크플로우 생성 완료: {name} (id={workflow_id})")

        # 활성화
        await client.post(
            f"{base}/api/v1/workflows/{workflow_id}/activate",
            headers=headers
        )
        logger.info(f"워크플로우 활성화 완료: {name}")

        return workflow_id