# app\domains\action\schemas.py
from pydantic import BaseModel
from typing import Optional, List

# =================================================================
# 공통
# =================================================================
class ExportResponse(BaseModel):
    status:str = "processing"

# =================================================================
# slack
# =================================================================
class SlackExportRequest(BaseModel):
    channel_id: Optional[str] = None
    include_action_items: bool = True

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
    attendee_emails: List[str]
    duration_minutes: int = 60

class NextMeetingSuggestResponse(BaseModel):
    slots: List[str]

class NextMeetingRegisterRequest(BaseModel):
    title: str
    scheduled_at: str
    participant_ids: List[int]