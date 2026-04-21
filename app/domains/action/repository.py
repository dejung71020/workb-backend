# app\domains\action\repository.py
from sqlalchemy.orm import Session
from typing import List, Optional

from app.domains.action.models import ActionItem
from app.domains.intelligence.models import MeetingMinute
from app.domains.meeting.models import Meeting
from app.domains.user.models import User

def get_meeting(db: Session, meeting_id: int) -> Optional[Meeting]:
    return db.query(Meeting).filter(Meeting.id == meeting_id).first()

def get_meeting_minute(db: Session, meeting_id: int) -> Optional[MeetingMinute]:
    return db.query(MeetingMinute).filter(MeetingMinute.meeting_id == meeting_id).first()

def get_action_items(db: Session, meeting_id: int) -> List[ActionItem]:
    return db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()

def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()