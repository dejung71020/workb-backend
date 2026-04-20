# app/domains/action/services/google.py
from sqlalchemy.orm import Session
from typing import List

async def export_google_calendar(
        db: Session,
        workspace_id: int,
        meeting_id: int
) -> None:
    pass

async def suggest_next_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        attendee_emails: List[str],
) -> List[str]:
    pass

async def register_next_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        title: str,
        scheduled_at: str
) -> None:
    pass