# app/infra/clients/slack.py
import logging
from typing import Dict, Any, List, Optional
from .base import BaseClient

logger = logging.getLogger(__name__)

class SlackClient(BaseClient):
    """
    Slack API 직접 호출 클라이언트
    integrations 테이블의 access_token(bot_token) 사용
    """
    def __init__(self, bot_token: str):
        super().__init__(
            base_url="https://slack.com/api",
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        )

    async def send_message(
            self, 
            channel: str, 
            text: str, 
            blocks: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Slack 채널에 메세지 전송

        args:
            channel: 채널 ID
            text: 메시지 본문
            blocks: Block Kit 블록 리스트
        """
        payload: Dict[str, Any] = {
            "channel": channel,
            "text": text
        }
        if blocks:
            payload['blocks'] = blocks
        
        return await self._request("POST", "/chat.postMessage", json=payload)
    
    async def get_user_id_by_email(self, email: str) -> str:
        """
        이메일로 Slack user_id 조회
        DM 하기 위해 user_id를 알아야 함.
        """
        result = await self._request(
            "GET", "/users.lookupByEmail", params={"email": email}
        )
        return result['user']['id']
    
    async def open_dm(self, user_id: str) -> str:
        """
        DM 채널 만들고, 채널 ID 반환
        """
        result = await self._request(
            "POST", "/conversations.open", json={"users": user_id}
        )
        return result['channel']['id']
    
    async def send_dm_by_email(self, email: str, text: str) -> Dict[str, Any]:
        """
        이메일 기반 DM 발송

        args:
            email: 수신자 이메일
            text: 내용
        """
        user_id = await self.get_user_id_by_email(email)
        channel_id = await self.open_dm(user_id)
        return await self.send_message(channel=channel_id, text=text)
    
    async def send_minutes(
            self,
            channel: str,
            meeting_title: str,
            minutes_text: str,
            action_items: Optional[List[str]] = None,
            link_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        회의록을 Slack Block Kit 형식으로 전송.

        args:
            channel : 채널명
            meeting_title: 회의 제목
            minutes_text: 회의록 내용
            action_items: 액션 아이템 리스트 (선택)
            link_url: 서비스 내 회의록 링크 (선택)
        """
        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{meeting_title}",
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": minutes_text[:3000],
                },
            },
        ]

        if action_items:
            action_text = "\n".join(f"• {item}" for item in action_items)
            blocks += [
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"액션 아이템\n{action_text}"
                    }
                }
            ]
        
        if link_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "회의록 보기"
                        },
                        "url": link_url,
                        "style": "primary",
                    }
                ],
            })
        
        return await self.send_message(
            channel=channel,
            text=f"[{meeting_title}] 회의록이 도착했습니다.",
            blocks=blocks
        )