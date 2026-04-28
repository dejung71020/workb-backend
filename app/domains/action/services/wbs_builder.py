# app/domains/action/services/wbs_builder.py
from sqlalchemy.orm import Session
from app.domains.action import repository
from app.domains.action.mongo_repository import get_meeting_summary

_PRIORITY_MAP = {
    "high":   "high",
    "urgent": "high",
    "normal": "medium",
    "low":    "low",
    "medium": "medium",
}

def _map_priority(raw: str) -> str:
    return _PRIORITY_MAP.get(str(raw).lower(), "medium")

async def build_wbs_template(db: Session, meeting_id: int) -> dict:
    epics = repository.get_wbs_epics(db, meeting_id)
    if epics:
        return _from_wbs_table(db, epics)
    
    summary = get_meeting_summary(meeting_id)
    if not summary:
        raise ValueError(f"회의 요약이 없습니다. (meeting_id: {meeting_id})")
    return _persist_and_build(db, meeting_id, summary)

def _from_wbs_table(db: Session, epics: list) -> dict:
    result = []
    for epic in epics:
        tasks = repository.get_wbs_tasks_by_epic(db, epic.id)
        task_list = []
        for t in tasks:
            user = repository.get_user(db, t.assignee_id) if t.assignee_id else None
            task_list.append({
                "id":       t.id,
                "title":    t.title,
                "assignee": user.name if user else "",
                "due_date": str(t.due_date) if t.due_date else None,
                "priority": t.priority.value,
                "urgency": "normal",
            })
        result.append({
            "id": epic.id,
            "title": epic.title,
            "tasks": task_list
        })
    return {
        "epics": result
    }

def _persist_and_build(
        db: Session, 
        meeting_id: int, 
        summary: dict
) -> dict:
    result = []

    # Epic 1-N : discussion_items 주제별 Epic
    discussion_items = summary.get("discussion_items", [])
    for i, item in enumerate(discussion_items):
        topic = item.get("topic", f"논의 주제 {i + 1}")
        epic = repository.save_wbs_epic(db, meeting_id, topic, order_index=i)
        result.append({
            "id": epic.id, 'title': epic.title, "tasks": []
        })
    
    # 마지막 Epic: action_items 전체를 실행 과제로 묶기
    action_items = summary.get("action_items", [])
    if action_items:
        action_epic = repository.save_wbs_epic(db, meeting_id, "실행 과제", order_index=len(discussion_items))
        task_list = []
        for a in action_items:
            assignee = a.get("assignee", '')
            # 담당자 이름을 제목에 포함
            title = a.get('content', '')
            task = repository.save_wbs_task(
                  db=db,
                  epic_id=action_epic.id,
                  title=title,
                  assignee_name=assignee or None,
                  priority=_map_priority(a.get("priority", "medium")),
              )
            task_list.append({
                "id":       task.id,
                "title":    task.title,
                "due_date": a.get("deadline"),
                "priority": a.get("priority", "normal"),
                "urgency":  a.get("urgency", "normal"),
            })
        result.append({
            "id": action_epic.id, "title": "실행 과제", "tasks": task_list
            })

    return {"epics": result}