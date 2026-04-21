# app\api\v1\api_router.py
from fastapi import APIRouter

from app.domains.action.router import router as action_router
from app.domains.integration.router import router as integration_router
from app.domains.knowledge.router import router as knowledge_router
from app.domains.user.router import router as user_router
from app.domains.vision.router import router as vision_router
from app.domains.workspace.router import router as workspace_router

api_router = APIRouter()

api_router.include_router(user_router, prefix="/users", tags=["Users"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["Workspace"])
api_router.include_router(integration_router, prefix="/integrations", tags=["Integration"])
api_router.include_router(knowledge_router, prefix="/knowledges", tags=["Knowledge"])
api_router.include_router(action_router, prefix="/actions", tags=["Actions"])
api_router.include_router(vision_router, prefix="/visions", tags=["Vision"])
