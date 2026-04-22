# app/domains/action/services/minutes_builder.py
from sqlalchemy.orm import Session
from app.domains.intelligence.models import MeetingMinute, MinuteStatus
from app.domains.action.mongo_repository import get_meeting_summary

def build_and_save_minutes(db: Session, meeting_id: int) -> MeetingMinute:
    '''
    
    '''
    pass