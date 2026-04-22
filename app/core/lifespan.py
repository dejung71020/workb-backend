# app/core/lifespan.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.infra.clients.session_manager import ClientSessionManager
from app.infra.database.base import Base
from app.infra.database.session import engine
from scripts.seed import seed_test_data

# 모든 모델을 import해야 Base가 테이블을 인식함
from app.domains.user.models import User
from app.domains.workspace.models import Workspace, InviteCode, WorkspaceMember, DeviceSetting, Department
from app.domains.meeting.models import Meeting, MeetingParticipant, Agenda, AgendaItem, SpeakerProfile
from app.domains.intelligence.models import Decision, MeetingMinute, MinutePhoto, ReviewRequest
from app.domains.action.models import ActionItem, WbsEpic, WbsTask, Report
from app.domains.integration.models import Integration


def _reset_mysql_schema() -> None:
    """
    MySQL에서 순환 FK가 있어도 전체 테이블을 강제로 초기화합니다.
    """
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        table_rows = conn.execute(text("SHOW TABLES")).fetchall()
        for row in table_rows:
            table_name = row[0]
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    should_reset_db = settings.DEBUG and settings.RESET_DB_ON_STARTUP

    if should_reset_db:
        _reset_mysql_schema()
        print("🗑️  [DEBUG] 전체 테이블 삭제 완료")

    Base.metadata.create_all(bind=engine)
    print("✅  테이블 생성 완료")

    # [시작 시] HTTP 클라이언트 세션 초기화
    await ClientSessionManager.get_client()

    if should_reset_db:
        seed_test_data()

    yield
    
    # [종료 시] 연결 닫기
    await ClientSessionManager.close_client()
