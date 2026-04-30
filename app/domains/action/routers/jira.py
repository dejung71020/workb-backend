# app/domains/action/routers/jira.py
from fastapi import APIRouter, Depends, BackgroundTasks, Query, HTTPException
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.action.schemas import ExportResponse, JiraSyncResponse, JiraSyncItem
from app.domains.action.services.jira import export_jira, sync_from_jira
from app.domains.integration.repository import get_integration
from app.domains.integration.models import ServiceType

router = APIRouter()

@router.post("/export/jira", response_model=ExportResponse)
async def jira_export(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
):
    integration = get_integration(db, workspace_id, ServiceType.jira)
    if not integration or not integration.access_token:
        raise HTTPException(status_code=400, detail="지라 연동이 필요합니다. 설정 > 연동 관리에서 연결해주세요.")
    
    project_key = (integration.extra_config or {}).get("project_key")
    if not project_key:
        raise HTTPException(status_code=400, detail="프로젝트를 선택해주세요. 설정 > 연동 관리")
    
    background_tasks.add_task(
        export_jira,
        db=db,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
    )
    return ExportResponse(status="processing")

@router.get("/sync/jira", response_model=JiraSyncResponse)
async def sync_from_jira_route(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
):
    integration = get_integration(db, workspace_id, ServiceType.jira)
    if not integration:
        raise HTTPException(status_code=400, detail="JIRA 연동이 필요합니다. 설정 > 연동 관리에서 연동해주세요.")
    
    try:
        result = await sync_from_jira(db, workspace_id, meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JiraSyncResponse(
        changed=[JiraSyncItem(**item) for item in result['changed']],
        unchanged=result['unchanged'],
        synced_at=result['synced_at'],
    )
    