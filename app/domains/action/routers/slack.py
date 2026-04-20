# app/domains/action/routers/slack.py
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.action.schemas import SlackExportRequest, ExportResponse
from app.domains.action.services.slack import export_slack

router = APIRouter()

WORKSPACE_ID = 1 # 테스트용 추후 request로 받을거임
'''
    router : http://localhost:8000/api/v1/actions//meetings/{meeting_id}
'''

@router.post("/export/slack", response_model=ExportResponse)
async def export_to_slack(
    meeting_id: int,
    request: SlackExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    background_tasks.add_task(
        export_slack,
        db=db,
        workspace_id=WORKSPACE_ID,
        meeting_id=meeting_id,
        channel_id=request.channel_id,
        include_action_items=request.include_action_items,
    )
    return ExportResponse()