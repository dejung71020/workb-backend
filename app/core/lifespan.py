# app/core/lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.infra.clients.session_manager import ClientSessionManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션의 시작과 종료 시 실행되는 로직
    """
    # [시작 시] 전역 비동기 클라이언트 세션을 초기화하여 커넥션 풀을 생성   
    await ClientSessionManager.get_client()

    yield # 애플리케이션 실행 중

    # [종료 시] 열려 있는 모든 외부 인프라 연결을 닫음
    await ClientSessionManager.close_client()