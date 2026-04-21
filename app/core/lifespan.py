# app/core/lifespan.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DEBUG:
        Base.metadata.drop_all(bind=engine)
        print("🗑️  [DEBUG] 전체 테이블 삭제 완료")

    Base.metadata.create_all(bind=engine)
    print("✅  테이블 생성 완료")

    await ClientSessionManager.get_client()

    if settings.DEBUG:
        seed_test_data()

    yield

    await ClientSessionManager.close_client()
