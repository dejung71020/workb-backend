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

class UpdateMeetingRequest(BaseModel):
    title: str
    meeting_type: str
    scheduled_at: datetime
    participant_ids: list[int] = Field(default_factory=list)

class DeleteMeetingResponse(BaseModel):
    success: bool = True
    message: str = "OK"


# ── Meeting search (GET /api/v1/knowledge/workspaces/{id}/meetings/search) ─


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


# ── Meeting history (GET /api/v1/meetings/workspaces/{id}/history) ─────────


class MeetingHistoryItemOut(BaseModel):
    id: int
    title: str
    status: str
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None


class MeetingHistoryResponse(BaseModel):
    total: int
    page: int
    meetings: list[MeetingHistoryItemOut] = Field(default_factory=list)


# ── Agenda (POST/PATCH/DELETE under /api/v1/meetings/{meeting_id}/...) ───────


class AgendaItemCreate(BaseModel):
    title: str
    presenter_id: Optional[int] = None
    estimated_minutes: Optional[int] = None
    reference_url: Optional[str] = None
    order_index: int


class AgendaBulkCreateRequest(BaseModel):
    items: list[AgendaItemCreate] = Field(..., min_length=1)


class AgendaItemCreatedOut(BaseModel):
    id: int
    title: str
    order_index: int


class AgendaBulkCreateResponse(BaseModel):
    success: bool = True
    agenda_id: int
    items: list[AgendaItemCreatedOut] = Field(default_factory=list)
    message: str = "OK"


class AgendaItemPatch(BaseModel):
    title: Optional[str] = None
    presenter_id: Optional[int] = None
    estimated_minutes: Optional[int] = None
    reference_url: Optional[str] = None
    order_index: Optional[int] = None


class AgendaItemOut(BaseModel):
    id: int
    agenda_id: int
    title: str
    presenter_id: Optional[int] = None
    estimated_minutes: Optional[int] = None
    reference_url: Optional[str] = None
    order_index: int


class AgendaItemPatchResponse(BaseModel):
    success: bool = True
    data: AgendaItemOut
    message: str = "OK"


class AgendaItemDeleteResponse(BaseModel):
    success: bool = True
    message: str = "OK"
