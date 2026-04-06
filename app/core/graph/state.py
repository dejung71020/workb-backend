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