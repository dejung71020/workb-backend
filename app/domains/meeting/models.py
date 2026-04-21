# app\domains\meeting\models.py
from sqlalchemy import Column, BigInteger, String, Enum, DateTime, Boolean, ForeignKey, Integer, func
from app.infra.database.base import Base
import enum

class MeetingStatus(str, enum.Enum):
    scheduled   = "scheduled"
    in_progress = "in_progress"
    done        = "done"

class DiarizationMethod(str, enum.Enum):
    stereo      = "stereo"
    diarization = "diarization"

class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id = Column(BigInteger, ForeignKey("workspaces.id"), nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    meeting_type = Column(String(100), nullable=True)
    status = Column(Enum(MeetingStatus), default=MeetingStatus.scheduled)
    room_name = Column(String(100), nullable=False, default="미지정")
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    google_calendar_event_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    meeting_id = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    speaker_label = Column(String(20), nullable=True)
    is_host = Column(Boolean, default=False)

class Agenda(Base):
    __tablename__ = "agendas"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    meeting_id = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)

class AgendaItem(Base):
    __tablename__ = "agenda_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agenda_id = Column(BigInteger, ForeignKey("agendas.id"), nullable=False)
    title = Column(String(200), nullable=False)
    presenter_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    reference_url = Column(String(500), nullable=True)
    order_index = Column(Integer, nullable=False)

class SpeakerProfile(Base):
    __tablename__ = "speaker_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(BigInteger, ForeignKey("workspaces.id"), nullable=False)
    voice_model_path = Column(String(500), nullable=True)
    diarization_method = Column(Enum(DiarizationMethod), nullable=False)
    is_verified = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
