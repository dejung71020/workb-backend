# app/domains/action/routers/wbs.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.action import repository
from app.domains.action.schemas import (
    WbsPageResponse, WbsEpicResponse, WbsTaskResponse,
    WbsEpicCreateRequest, WbsEpicPatchRequest,
    WbsTaskCreateRequest, WbsTaskPatchRequest,
    ExportResponse,
)
from app.domains.action.services.wbs_builder import build_wbs_template
from app.domains.user.dependencies import require_workspace_admin, require_workspace_member

# http://localhost:8000/api/v1/actions/meetings/{meeting_id}/wbs
router = APIRouter()

@router.get("/wbs", response_model=WbsPageResponse)
async def get_wbs(
        meeting_id: int,
        workspace_id: int = Query(..., description="워크스페이스 ID"),
        db: Session = Depends(get_db),
        _member = Depends(require_workspace_member),
):
    epics = repository.get_wbs_epics(db, meeting_id)
    result = []
    for epic in epics:
        tasks = repository.get_wbs_tasks_by_epic(db, epic.id)
        result.append(WbsEpicResponse(
            id=epic.id,
            title=epic.title,
            order_index=epic.order_index,
            tasks=[WbsTaskResponse(
                id=t.id,
                epic_id=epic.id,
                title=t.title,
                assignee_id=t.assignee_id,
                priority=t.priority.value if hasattr(t.priority, 'value') else t.priority,
                due_date=t.due_date,
                progress=t.progress,
                status=t.status.value if hasattr(t.status, 'value') else t.status,
            ) for t in tasks]
        ))
    return WbsPageResponse(epics=result)
    
@router.post("/wbs/generate", response_model=WbsPageResponse)
async def generate_wbs(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    await build_wbs_template(db, meeting_id)
    epics = repository.get_wbs_epics(db, meeting_id)
    result = []
    for epic in epics:
        tasks = repository.get_wbs_tasks_by_epic(db, epic.id)
        result.append(WbsEpicResponse(
            id=epic.id,
            title=epic.title,
            order_index=epic.order_index,
            tasks=[WbsTaskResponse(
                id=t.id,
                epic_id=epic.id,
                title=t.title,
                assignee_id=t.assignee_id,
                priority=t.priority.value if hasattr(t.priority, 'value') else t.priority,
                due_date=t.due_date,
                progress=t.progress,
                status=t.status.value if hasattr(t.status, 'value') else t.status,
            ) for t in tasks]
        ))
    return WbsPageResponse(epics=result)

@router.post("/wbs/epics", response_model=WbsEpicResponse)
def create_epic(
    meeting_id: int,
    body: WbsEpicCreateRequest,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    epics = repository.get_wbs_epics(db, meeting_id)
    order = body.order_index if body.order_index is not None else len(epics)
    epic = repository.save_wbs_epic(db, meeting_id, body.title, order)
    return WbsEpicResponse(
        id=epic.id,
        title=epic.title,
        order_index=epic.order_index,
        tasks=[]
    )

@router.post("/wbs/tasks", response_model=WbsTaskResponse)
def create_task(
    meeting_id: int,
    body: WbsTaskCreateRequest,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    task = repository.save_wbs_task(
        db, body.epic_id, body.title,
        body.assignee_id,
        body.priority or "medium", body.due_date,
    )
    return WbsTaskResponse(
        id=task.id,
        epic_id=task.epic_id,
        title=task.title,
        assignee_id=task.assignee_id,
        priority=task.priority.value if hasattr(task.priority, 'value') else task.priority,
        due_date=task.due_date,
        progress=task.progress,
        status=task.status.value if hasattr(task.status, 'value') else task.status,
    )

@router.patch("/wbs/epics/{epic_id}", response_model=WbsEpicResponse)
def patch_epic(
    meeting_id: int,
    epic_id: int,
    body: WbsEpicPatchRequest,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    epic = repository.update_wbs_epic(db, epic_id, body.title, order_index=body.order_index)
    if not epic:
        raise HTTPException(status_code=404, detail="Epic을 찾을 수 없습니다.")
    tasks = repository.get_wbs_tasks_by_epic(db, epic_id)
    return WbsEpicResponse(
        id=epic_id,
        title=epic.title,
        order_index=epic.order_index,
        tasks=[WbsTaskResponse(
            id=t.id,
            epic_id=epic_id,
            title=t.title,
            assignee_id=t.assignee_id,
            priority=t.priority.value if hasattr(t.priority, "value") else t.priority,
            due_date=t.due_date,
            progress=t.progress,
            status=t.status.value if hasattr(t.status, 'value') else t.status,
        ) for t in tasks]
    ) 

@router.patch("/wbs/tasks/{task_id}", response_model=WbsTaskResponse)
def patch_task(
    meeting_id: int,
    task_id: int,
    body: WbsTaskPatchRequest,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    task = repository.update_wbs_task(
        db=db,
        task_id=task_id,
        title=body.title,
        assignee_id=body.assignee_id,
        priority=body.priority,
        due_date=body.due_date,
        progress=body.progress,
        status=body.status
    )
    if not task:
        raise HTTPException(status_code=404, detail="TASK를 찾을 수 없습니다.")
    return WbsTaskResponse(
        id=task.id, epic_id=task.epic_id, title=task.title,
        assignee_id=task.assignee_id,
        priority=task.priority.value if hasattr(task.priority, 'value') else task.priority,
        due_date=task.due_date, 
        progress=task.progress,
        status=task.status.value if hasattr(task.status, 'value') else task.status,
    )

@router.delete("/wbs/epics/{epic_id}", response_model=ExportResponse)
def delete_epic(
    meeting_id: int,
    epic_id: int,
    workspace_id: int = Query(..., description='워크스페이스 ID'),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    ok = repository.delete_wbs_epic(db, epic_id)
    if not ok:
        raise HTTPException(status_code=404, detail="EPIC을 찾을 수 없습니다.")
    return ExportResponse(status="ok")

@router.delete("/wbs/tasks/{task_id}", response_model=ExportResponse)
def delete_task(
    meeting_id: int,
    task_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    ok = repository.delete_wbs_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="TASK를 찾을 수 없습니다.")
    return ExportResponse(status="ok")