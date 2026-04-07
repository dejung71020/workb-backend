# app\api\v1\api_router.py
from fastapi import APIRouter

# 각 도메인별 라우터 임포트
from app.domains.meeting.router import router as meeting_router
from app.domains.intelligence.router import router as intelligence_router
from app.domains.knowledge.router import router as knowledge_router
from app.domains.action.router import router as action_router
from app.domains.vision.router import router as vision_router
from app.domains.user.router import router as user_router
from app.domains.workspace.router import router as workspace_router
from app.domains.integration.router import router as integration_router

api_router = APIRouter()

# 1. 사용자 및 인증 도메인 (회원가입, 로그인, 음성 특징 등록)
api_router.include_router(user_router, prefix="/users", tags=["Users"])

# 2. 회의 도메인 (실시간 회의 시작, 음성 스트림 처리, 과거 기록/스크립트 조회)
api_router.include_router(meeting_router, prefix="/meetings", tags=["Meetings"])

# 3. 인텔리전스 도메인 (회의 요약본 조회, 결정사항 리스트 확인)
api_router.include_router(intelligence_router, prefix="/intelligence", tags=["Intelligence"])

# 4. 지식 베이스 도메인 (과거 자료 검색, 챗봇 대화 엔드포인트)
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["Knowledge"])

# 5. 액션 도메인 (생성된 WBS 조회, 외부 툴 연동 상태 확인)
api_router.include_router(action_router, prefix="/actions", tags=["Actions"])

# 6. 비전 도메인 (스크린샷 분석 결과 조회)
api_router.include_router(vision_router, prefix="/vision", tags=["Vision"])

# 7. 사용자 로그인, 회원가입 도메인
api_router.include_router(user_router, prefix="/users", tags=["Users"])

# 8. 워크스페이스 도메인
api_router.include_router(workspace_router, prefix="/workspaces", tags=["Workspace"])

# 9. API 연동 통합 도메인
api_router.include_router(integration_router, prefix="/integrations", tags=["Integration"])
