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
        assignee_name: Optional[str] = None,
        priority: str = Priority.medium,
        due_date: Optional[date] = None,
) -> WbsTask:
    task = WbsTask(
        epic_id=epic_id,
        title=title,
        assignee_id=assignee_id,
        assignee_name=assignee_name,
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

# =================================================================
# WBS
# =================================================================
def get_wbs_epic(db: Session, epic_id: int) -> Optional[WbsEpic]:
    return db.query(WbsEpic).filter(WbsEpic.id==epic_id).first()

def get_wbs_task(db: Session, task_id: int) -> Optional[WbsTask]:
    return db.query(WbsTask).filter(WbsTask.id==task_id).first()

def update_wbs_epic(
        db: Session,
        epic_id: int,
        title: Optional[str] = None,
        order_index: Optional[int] = None, 
) -> Optional[WbsEpic]:
    epic = get_wbs_epic(db, epic_id)
    if not epic:
        return None
    if title is not None:
        epic.title = title
    if order_index is not None:
        epic.order_index = order_index
    db.commit()
    db.refresh(epic)
    return epic

def update_wbs_task(
        db: Session,
        task_id: int,
        title: Optional[str] = None,
        assignee_id: Optional[int] = None,
        assignee_name: Optional[str] = None,
        priority: Optional[str] = None,
        due_date: Optional[date] = None,
        progress: Optional[int] = None,
        status: Optional[str] = None,
) -> Optional[WbsTask]:
    task = get_wbs_task(db, task_id)
    if not task:
        return None
    if title is not None:
        task.title = title
    if assignee_id is not None:
        task.assignee_id = assignee_id
    if assignee_name is not None:
        task.assignee_name = assignee_name
    if priority is not None:
        task.priority = priority
    if due_date is not None:
        task.due_date = due_date
    if progress is not None:
        task.progress = max(0, min(100, progress))
    if status is not None:
        task.status = status
    db.commit()
    db.refresh(task)
    return task

def delete_wbs_epic(db: Session, epic_id: int) -> bool:
    epic = get_wbs_epic(db, epic_id)
    if not epic:
        return False
    db.query(WbsTask).filter(WbsTask.epic_id == epic_id).delete()
    db.delete(epic)
    db.commit()
    return True

def delete_wbs_task(db: Session, task_id: int) -> bool:
    task = get_wbs_task(db, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True