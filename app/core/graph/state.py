# app\core\graph\state.py
from typing import TypedDict, List, Optional, Annotated
import operator

class SharedState(TypedDict):
    # 흐름 제어
    next_node: str               # 다음에 실행할 노드명
    current_scenario: str        # 현재 진행 중인 시나리오 ID
    
    # Meeting 도메인 (Scribe)
    transcript: Annotated[List[dict], operator.add] # [{speaker: str, text: str, timestamp: str}]
    
    # Knowledge 도메인 (Researcher)
    search_query: str            # 검색을 위한 쿼리
    retrieved_docs: List[dict]   # 검색된 과거/외부 문서 리스트
    chat_history: Annotated[List[dict], operator.add] # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    user_question: str           # 사용자가 챗봇에게 던진 질문
    chat_response: str           # 챗봇의 최종 답변
    
    # Intelligence 도메인 (Analyst)
    summary: str                 # 요약 결과
    decisions: List[str]         # 결정된 사항들
    
    # Vision 도메인 (Interpreter)
    screenshot_analysis: str     # 캡처 이미지 해석 텍스트
    
    # Action 도메인 (Architect)
    wbs: List[dict]              # [{task: str, owner: str, due: str}]
    external_links: dict         # Jira 티켓 번호, 엑셀 다운로드 링크 등
    
    # Quality 도메인 (QA/Ops)
    accuracy_score: float        # 결과물 정확도 (0~1)
    errors: List[str]            # 발생한 에러 로그


    # 웹 컨텍스트 정보 추가
    workspace_id: str            # 현재 워크스페이스 ID
    meeting_id: str              # 현재 회의 고유 ID
    agenda: List[dict]           # 웹에서 설정한 안건 목록 [{"topic": str, "speaker": str}]
    integration_settings: dict   # 연동된 서비스 목록 및 권한 정보
    
    # AI 기능용 확장
    previous_context: str        # [AI] 이전 회의 맥락 정리 데이터
    realtime_actions: List[dict] # [AI] 실시간 감지된 액션 아이템