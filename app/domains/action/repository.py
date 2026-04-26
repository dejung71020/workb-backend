# app\domains\action\repository.py
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.domains.action.models import ActionItem, WbsEpic, WbsTask, Report, ReportFormat, Priority
from app.domains.intelligence.models import MeetingMinute
from app.domains.meeting.models import Meeting
from app.domains.user.models import User


# ----------------------------------------------------------------------
def get_meeting(db: Session, meeting_id: int) -> Optional[Meeting]:
    return db.query(Meeting).filter(Meeting.id == meeting_id).first()

def get_meeting_minute(db: Session, meeting_id: int) -> Optional[MeetingMinute]:
    return db.query(MeetingMinute).filter(MeetingMinute.meeting_id == meeting_id).first()

def get_action_items(db: Session, meeting_id: int) -> List[ActionItem]:
    return db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()

def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

# -----------보고서-------------------------------------------------------
def save_report(
        db: Session,
        meeting_id: int,
        created_by: int,
        format: ReportFormat,
        title: str,
        content: Optional[str] = None,
        file_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
) -> Report:
    report = Report(
        meeting_id=meeting_id,
        created_by=created_by,
        format=format,
        title=title,
        content=content,
        file_url=file_url,
        thumbnail_url=thumbnail_url,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report

def get_report(db: Session, report_id: int) -> Optional[Report]:
    return db.query(Report).filter(Report.id == report_id).first()

def get_reports(db: Session, meeting_id: int) -> List[Report]:
    return db.query(Report).filter(Report.meeting_id==meeting_id).order_by(Report.created_at.desc()).all()

def update_report(db: Session, report_id: int, content: str) -> Optional[Report]:
    report = get_report(db, report_id)
    if report:
        report.content = content    
        db.commit()
        db.refresh(report)
    return report

# --- WBS 조회 ---
def get_wbs_epics(db: Session, meeting_id: int) -> List[WbsEpic]:
    return (
        db.query(WbsEpic).filter(WbsEpic.meeting_id == meeting_id)
        .order_by(WbsEpic.order_index)
        .all()
    )

def get_wbs_tasks_by_epic(db: Session, epic_id: int) -> List[WbsTask]:
    return db.query(WbsTask).filter(WbsTask.epic_id == epic_id).all()

# --- WBS 생성 ---
def save_wbs_epic(
        db: Session, 
        meeting_id: int, 
        title: str, 
        order_index: int
) -> WbsEpic:
    epic = WbsEpic(
        meeting_id=meeting_id,
        title=title,
        order_index=order_index
    )
    db.add(epic)
    db.commit()
    db.refresh(epic)
    return epic

def save_wbs_task(
        db: Session,
        epic_id: int,
        title: str,
        assignee_id: Optional[int] = None,
        priority: str = Priority.medium,
        due_date: Optional[date] = None,
) -> WbsTask:
    task = WbsTask(
        epic_id=epic_id,
        title=title,
        assignee_id=assignee_id,
        priority=priority if priority else Priority.medium,
        due_date=due_date
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

# --- 외부 ID 저장 ------------------------------------------

def update_epic_notion_id(db: Session, epic_id: int, notion_page_id: str) -> None:
    db.query(WbsEpic).filter(WbsEpic.id == epic_id).update({
        "notion_page_id": notion_page_id
    })
    db.commit()

def update_task_notion_id(db: Session, task_id: int, notion_page_id: str) -> None:
    db.query(WbsTask).filter(WbsTask.id == task_id).update({
        "notion_page_id": notion_page_id
    })
    db.commit()

def update_epic_jira_id(db: Session, epic_id: int, jira_epic_id: str) -> None:
    db.query(WbsEpic).filter(WbsEpic.id == epic_id).update({
        "jira_epic_id": jira_epic_id
    })
    db.commit()

def update_task_jira_id(db: Session, task_id: int, jira_issue_id: str) -> None:
    db.query(WbsTask).filter(WbsTask.id == task_id).update({
        "jira_issue_id": jira_issue_id
    })
    db.commit()