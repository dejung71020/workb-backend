# app\domains\action\schemas.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from datetime import date as date_type

# =================================================================
# 공통
# =================================================================
class ExportResponse(BaseModel):
    status:str = "processing"

# =================================================================
# 회의록
# =================================================================
class MinutesResponse(BaseModel):
    meeting_id: int
    content:    Optional[str] = None
    updated_at: datetime

class MinutesPatchRequest(BaseModel):
    content: str

# =================================================================
# 보고서
# =================================================================
class ReportResponse(BaseModel):
    id:             int
    format:         str
    title:          str
    thumbnail_url:  Optional[str] = None
    updated_at:     datetime

    class Config:
        from_attributes = True

class ReportGenerateRequest(BaseModel):
    format: str # markdown | excel | wbs | html

class ReportPatchRequest(BaseModel):
    content: str
    
# =================================================================
# slack
# =================================================================
class SlackExportRequest(BaseModel):
    channel_id: Optional[str] = None
    include_action_items: bool = True
    include_reports: bool = False

# =================================================================
# notion
# =================================================================
class NotionExportRequest(BaseModel):
    page_id: Optional[str] = None
    include_wbs: bool = False

# =================================================================
# jira
# =================================================================



# =================================================================
# kakao
# =================================================================
class KakaoExportRequest(BaseModel):
    include_action_items: bool = True

# =================================================================
# google calendar
# =================================================================
class NextMeetingSuggestRequest(BaseModel):
    duration_minutes: int = 60

class NextMeetingSuggestResponse(BaseModel):
    slots: List[str]

class NextMeetingRegisterRequest(BaseModel):
    title: str
    scheduled_at: str
    participant_ids: List[int]
    attendee_emails: List[str] = []

class NextMeetingRegisterResponse(BaseModel):
    event_id: str

class NextMeetingUpdateRequest(BaseModel):
    title: str | None = None
    scheduled_at: str | None = None
    duration_minutes: int = 60
    attendee_emails: List[str] | None = None
    description: str | None = None

# =================================================================
# WBS
# =================================================================
class WbsTaskResponse(BaseModel):
    id:          int
    epic_id:     int
    title:       str
    assignee_id: Optional[int] = None
    priority:    str
    due_date:    Optional[date_type] = None
    progress:    int
    status:      str

    class Config:
        from_attributes = True

class WbsEpicResponse(BaseModel):
    id:          int
    title:       str
    order_index: int
    tasks:       List[WbsTaskResponse] = []

    class Config:
        from_attributes = True

class WbsPageResponse(BaseModel):
    epics: List[WbsEpicResponse]

class WbsEpicCreateRequest(BaseModel):
    title:       str
    order_index: Optional[int] = None

class WbsEpicPatchRequest(BaseModel):
    title:       Optional[str] = None
    order_index: Optional[int] = None

class WbsTaskCreateRequest(BaseModel):
    epic_id:     int
    title:       str
    assignee_id: Optional[int] = None
    priority:    Optional[str] = "medium"
    due_date:    Optional[date_type] = None

class WbsTaskPatchRequest(BaseModel):
    title:       Optional[str] = None
    assignee_id: Optional[int] = None
    priority:    Optional[str] = None
    due_date:    Optional[date_type] = None
    progress:    Optional[int] = None
    status:      Optional[str] = None