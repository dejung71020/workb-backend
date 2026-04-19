# app/infra/clients/kakao.py
import logging
from typing import Dict, Any
from .base import BaseClient

class KakaoClient(BaseClient):
    """
    카카오톡 알림 클라이언트.
    """
    def __init__(self, api_key: str):
        super().__init__(
            base_url="https://kapi.kakao.com",
            headers={
                "Authorization": f"KakaoAK {api_key}",
                "Content_Type": "application/x-www-form-urlencoded",
            }
        )