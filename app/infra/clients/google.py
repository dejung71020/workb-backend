# app\infra\clients\google.py
import logging
from typing import Dict, Any, List, Optional
from .base import BaseClient

logger = logging.getLogger(__name__)

class GoogleCalendarClient(BaseClient):
    """
    Google Calendar API 직접 호출 클라이언트.
    integrations 테이블의 access_token 사용.
    토큰 만료는 service 에서 판단
    """
    def __init__(self, access_token: str):
        super().__init__(
            base_url="https://www.googleapis.com/calendar/v3",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
        )

    async def create_event(
            self,
            title: str,
            start_datetime: str,
            end_datetime: str,
            attendees: Optional[List[str]] = None,
            description: str = "",
            calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Google Calendar 일정 생성.

        args:
            title: 일정 제목
            start_datetime: ISO 8601 형식 2025-05-01T10:10:00
            end_datetime: 
            attendees: 참석자 이메일 리스트
            description: 일정 설명 (선택)
            calendar_id: 캘린더 ID, 데이터베이스 기본키
        """
        body: Dict[str, Any] = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_datetime,
                "timeZone": "Asia/Seoul"
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": "Asia/Seoul"
            },
        }
        if attendees:
            body["attendees"] = [{
                "email": email
        } for email in attendees]

        return await self._request(
            "POST", f"/calendars/{calendar_id}/events",
            json=body,
        )

    async def list_events(
            self,
            calendar_id: str = "primary",
            time_min: Optional[str] = None,
            max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        캘린더 일정 목록 조회.
        다음 회의 제안 때 기존 일정이 있는지 확인도 함.

        args:
            calendar_id: 캘린더 ID
            time_min: 조회 시작 시각 ISO 8601 2025-04-16T10:10:10
            max_results: 최대 반환 건수
        """
        params: Dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params['timeMin'] = time_min
        
        return await self._request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params=params
        )
    
    async def refresh_access_token(
            self, 
            refresh_token: str, 
            client_id: str, 
            client_secret: str
    ) -> Dict[str, Any]:
        """
        google_calendar_access_token을 갱신하는 함수

        return : {
            "access_token": "...",
            "expires_in": 3599
        }
        """
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            )
            response.raise_for_status()
            return response.json()