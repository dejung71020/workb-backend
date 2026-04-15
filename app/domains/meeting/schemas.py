# app\domains\meeting\schemas.py
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional


class CreateMeetingRequest(BaseModel):
    title: str
    meeting_type: str
    scheduled_at: datetime
    participant_ids: list[int] = Field(default_factory=list)
    sync_google_calendar: bool = False


class CreateMeetingResponseData(BaseModel):
    meeting_id: int
    title: str
    scheduled_at: datetime
    google_calendar_event_id: Optional[str] = None


class CreateMeetingResponse(BaseModel):
    success: bool = True
    data: CreateMeetingResponseData
    message: str = "OK"


# ── Meeting search (GET .../meetings/search) ───────────────────────────────


class MeetingSearchParams(BaseModel):
    """쿼리스트링을 서비스 레이어로 넘기기 위한 컨테이너."""

    keyword: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    participant_id: Optional[int] = None


class MeetingSearchParticipantOut(BaseModel):
    user_id: int
    name: str


class MeetingSearchItemOut(BaseModel):
    meeting_id: int
    title: str
    scheduled_at: Optional[datetime] = None
    participants: list[MeetingSearchParticipantOut] = Field(default_factory=list)
    summary: Optional[str] = None


class MeetingSearchData(BaseModel):
    meetings: list[MeetingSearchItemOut] = Field(default_factory=list)


class MeetingSearchResponse(BaseModel):
    success: bool = True
    data: MeetingSearchData
    message: str = "OK"
