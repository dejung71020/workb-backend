from __future__ import annotations
from app.core.ontology.schema import EntityType, ExtractionResult
from app.core.ontology.traverser import OntologyTraverser
from app.core.ontology.formatter import graph_to_text


# Literal → EntityType 매핑 (schema.py의 WsCategoryLiteral과 1:1 대응)
_WS_ENTITY_MAP: dict[str, EntityType] = {
    "WS_MEMBERS":     EntityType.WS_MEMBERS,
    "WS_DEPARTMENTS": EntityType.WS_DEPARTMENTS,
    "WS_REPORTS":     EntityType.WS_REPORTS,
    "WS_SCHEDULE":    EntityType.WS_SCHEDULE,
    "WS_DEVICE":      EntityType.WS_DEVICE,
    "WS_INTEGRATION": EntityType.WS_INTEGRATION,
    "WS_TASKS":       EntityType.WS_TASKS,
    "WS_DECISIONS":   EntityType.WS_DECISIONS,
}


async def build_ontology_context(
    question: str,
    workspace_id: int,
    llm,
) -> str:
    """
    질문 → 온톨로지 컨텍스트 텍스트 생성 메인 진입점.

    처리 흐름:
    1. llm.with_structured_output(ExtractionResult)로 엔티티 + 카테고리 + 날짜 추출
        - json.loads 파싱 없음, try/except 없음
        - Pydantic이 타입 검증까지 처리
    2. ExtractionResult 객체로 seed_entities 구성
    3. OntologyTraverser(max_depth=2)로 그래프 탐색
    4. graph_to_text()로 LLM 프롬프트용 텍스트 변환 후 반환

    반환값: knowledge_node의 system_prompt에 주입되는 컨텍스트 문자열.
    엔티티가 전혀 감지되지 않으면 빈 문자열 반환.
    """

    # ── Step 1: Structured Output으로 추출 (1회 호출) ────────────
    # with_structured_output: LLM이 ExtractionResult Pydantic 객체를 직접 반환
    # → json.loads, 마크다운 코드블록 제거, try/except 파싱 블록 전부 불필요
    structured_llm = llm.with_structured_output(ExtractionResult)

    extraction_prompt = f"""
    다음 질문에서 아래 정보를 추출하세요.

    질문: {question}

    entities 규칙:
    - 질문에 사람 이름이 있으면 type=User로 추가
    - 질문에 회의 이름이 있으면 type=Meeting으로 추가
    - 이름이 없으면 빈 배열

    workspace_categories 규칙 (해당하는 항목만 포함):
    - 멤버/팀원/인원/구성원/누가 있어 → WS_MEMBERS
    - 일정/예정/미팅/스케줄/언제 → WS_SCHEDULE
    - 연동/연결/Jira/Slack/캘린더/Google → WS_INTEGRATION
    - 장비/마이크/카메라/설정/디바이스 → WS_DEVICE
    - 태스크/WBS/할 일/작업/진행률 → WS_TASKS
    - 결정/확정/합의/결정사항 → WS_DECISIONS
    - 보고서/회의록/리포트 → WS_REPORTS
    - 부서/팀/조직 → WS_DEPARTMENTS
    - 해당 없으면 빈 배열

    date 규칙:
    - "지난달" → 이전 달 1일~말일 계산해서 YYYY-MM-DD 형식으로
    - "이번 주" → 이번 주 월요일~일요일
    - "오늘" → 오늘 날짜 하루
    - 날짜 언급 없으면 null
    """

    try:
        result: ExtractionResult = await structured_llm.ainvoke(extraction_prompt)
    except Exception:
        # with_structured_output 자체가 실패한 경우 (네트워크 오류 등)
        # 파싱 실패가 아닌 호출 실패이므로 빈 컨텍스트로 graceful 처리
        return ""

    ctx = {"date_from": result.date_from, "date_to": result.date_to}

    # ── Step 2: seed_entities 구성 ────────────────────────────────
    seed_entities: list[dict] = []

    # 단건 엔티티: id=None → traverser 내부에서 이름→PK 해소
    for ent in result.entities:
        seed_entities.append({
            "id": None,
            "type": ent.type,       # 딕셔너리 .get() 대신 Pydantic 속성 접근
            "name": ent.name,
            "ctx": ctx,
        })

    # WS_* 카테고리: entity_id 자리에 workspace_id를 넣어 전체 목록 fetch
    added_ws_types: set[str] = set()
    for category in result.workspace_categories:
        ws_type = _WS_ENTITY_MAP[category]  # Literal 보장으로 KeyError 불가
        if ws_type.value not in added_ws_types:
            seed_entities.append({
                "id": workspace_id,
                "type": ws_type.value,
                "name": ws_type.value,
                "ctx": ctx,
            })
            added_ws_types.add(ws_type.value)

    if not seed_entities:
        return ""

    # ── Step 3: 그래프 탐색 ───────────────────────────────────────
    traverser = OntologyTraverser(max_depth=2)
    graph = traverser.traverse(seed_entities, workspace_id)

    if not graph:
        return ""

    # ── Step 4: 텍스트 변환 ───────────────────────────────────────
    return graph_to_text(graph)
