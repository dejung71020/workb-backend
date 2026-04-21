# app\domains\action\models.py
from sqlalchemy import Column, String, Enum, DateTime, Boolean, ForeignKey, Text, Integer, Date, func
from app.infra.database.base import Base
import enum

class ActionStatus(str, enum.Enum):
    pending     = "pending"
    in_progress = "in_progress"
    done        = "done"

class TaskStatus(str, enum.Enum):
    todo        = "todo"
    in_progress = "in_progress"
    done        = "done"

class Priority(str, enum.Enum):
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"

class ReportFormat(str, enum.Enum):
    xlsx = "xlsx"
    pptx = "pptx"
    html = "html"

class ActionItem(Base):
    __tablename__ = "action_items"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id   = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    content      = Column(Text, nullable=False)
    assignee_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date     = Column(Date, nullable=True)
    status       = Column(Enum(ActionStatus), default=ActionStatus.pending)
    detected_at  = Column(DateTime, nullable=False)
    jira_issue_id = Column(String(100), nullable=True)


class WbsEpic(Base):
    __tablename__ = "wbs_epics"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id   = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    title        = Column(String(200), nullable=False)
    order_index  = Column(Integer, nullable=False)
    jira_epic_id = Column(String(100), nullable=True)


class WbsTask(Base):
    __tablename__ = "wbs_tasks"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    epic_id        = Column(Integer, ForeignKey("wbs_epics.id"), nullable=False)
    title          = Column(String(200), nullable=False)
    assignee_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    priority       = Column(Enum(Priority), default=Priority.medium)
    due_date       = Column(Date, nullable=True)
    progress       = Column(Integer, default=0)
    status         = Column(Enum(TaskStatus), default=TaskStatus.todo)
    jira_issue_id  = Column(String(100), nullable=True)
    notion_page_id = Column(String(100), nullable=True)
    created_at     = Column(DateTime, default=func.now(), nullable=False)
    updated_at     = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    format     = Column(Enum(ReportFormat), nullable=False)
    file_url   = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)