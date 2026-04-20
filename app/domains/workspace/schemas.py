# app\domains\workspace\schemas.py
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional

class WorkspaceListItem(BaseModel):
    id: int
    name: str
    role: str

    model_config = {"from_attributes": True}


class WorkspaceListResponse(BaseModel):
    success: bool = True
    workspaces: list[WorkspaceListItem] = Field(default_factory=list)
    message: str = "OK"

class WorkspaceMemberItem(BaseModel):
    user_id: int
    name: str
    department: Optional[str] = None
    role: str

class WorkspaceMembersResponse(BaseModel):
    success: bool = True
    members: list[WorkspaceMemberItem] = Field(default_factory=list)
    message: str = "OK"


class DashboardParticipantItem(BaseModel):
    user_id: int
    name: str


class MeetingItem(BaseModel):
    id: int
    title: str
    status: str
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    meeting_type: Optional[str] = None
    participants: list[DashboardParticipantItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MeetingsGroup(BaseModel):
    in_progress: list[MeetingItem] = []
    scheduled: list[MeetingItem] = []
    done: list[MeetingItem] = []


class WeeklySummary(BaseModel):
    total_count: int = 0
    total_duration_min: float = 0.0
    summary_cards: list = []


class PendingActionItemResponse(BaseModel):
    id: int
    content: str
    due_date: Optional[date] = None
    meeting_title: str


class NextMeetingSuggestion(BaseModel):
    suggested_at: datetime
    reason: str


class DashboardResponse(BaseModel):
    meetings: MeetingsGroup
    weekly_summary: WeeklySummary
    pending_action_items: list[PendingActionItemResponse] = []
    next_meeting_suggestion: Optional[NextMeetingSuggestion] = None
