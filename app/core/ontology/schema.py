from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal
from pydantic import BaseModel

# 온톨로지에서 다루는 "엔티티(개체)" 종류 정의
# 엔티티 = DB에 존재하는 핵심 개념 단위 (사람, 회의, 태스크 등)
class EntityType(str, Enum):
    # ── 단건 엔티티: 질문에서 이름이 언급된 특정 개체 ──────────────
    # 예) "박민준" → USER, "4월 기획 회의" → MEETING 
    USER = "User"
    MEETING = "Meeting"
    DECISION = "Decision"
    WBS_TASK = "WbsTask"
    DEPARTMENT = "Department"
    REPORT = "Report"

    # ── 워크스페이스 집합 엔티티: 카테고리 키워드로 트리거 ───────────
    # "장비 설정 알려줘" → WS_DEVICE, "연동 상태 보여줘" → WS_INTEGRATION
    # entity_id 자리에 workspace_id를 넣어 전체 목록을 가져온다
    WS_MEMBERS = "WsMembers"
    WS_DEPARTMENTS = "WsDepartments"
    WS_REPORTS = "WsReports"
    WS_SCHEDULE = "WsSchedule"
    WS_DEVICE = "WsDevice"
    WS_INTEGRATION = "WsIntegration"
    WS_TASKS       = "WsTasks"
    WS_DECISIONS   = "WsDecisions" 


# 엔티티 간의 "관계(엣지)" 종류 정의
# 예) User -[PARTICIPATED_IN]-> Meeting : 사용자가 회의에 참여했다
class RelationType(str, Enum):
    # ── 단건 엔티티 간 방향성 관계 ───────────────────────────────
    PARTICIPATED_IN = "participated_in" # User -> Meeting
    ASSIGNED_TO = "assigned_to"         # User -> WbsTask
    BELONGS_TO = "belongs_to"           # User -> Department
    HAS_TASK = "has_task"               # Meeting -> WbsTask
    HAS_DECISION = "has_decision"       # Meeting -> Decision
    HAS_REPORT = "has_report"           # Meeting -> Report
    HAS_MEMBER = "has_member"           # Meeting -> User

    # ── 워크스페이스 집합 조회 관계 ────────────────────────────── 
    LISTS_MEMBERS     = "lists_members" 
    LISTS_DEPARTMENTS = "lists_departments"
    LISTS_REPORTS     = "lists_reports"
    LISTS_SCHEDULE    = "lists_schedule"
    LISTS_DEVICE      = "lists_device"
    LISTS_INTEGRATION = "lists_integration"
    LISTS_TASKS       = "lists_tasks"
    LISTS_DECISIONS   = "lists_decisions"

# 관계 하나를 표현하는 데이터 구조
# from_entity -[type]-> to_entity 방향으로 fetch_ftn을 호출하면 관련 데이터를 가져옴
@dataclass
class Relation:
    type: RelationType      # 관계 종류
    from_entity: EntityType # 출발 엔티티 타입
    to_entity: EntityType   # 도착 엔티티 타입
    # (entity_id, workspace_id, ctx=None) → list[dict]
    # ctx: {"date_from": date, "date_to": date} 등 필터 조건 전달용
    fetch_fn: Callable[[int, int], list[dict]] 
    description: str        # 사람이 읽는 설명 (디버깅/로깅용)

    # ── infer_at_depth ──────────────────────────────────────────── 
    # "이 관계는 depth ≥ N 일 때만 탐색한다"는 브레이커(Circuit Breaker).
    #
    # depth=0 → seed 엔티티 자신
    # depth=1 → seed 의 직접 이웃 (1홉)
    # depth=2 → seed 의 이웃의 이웃 (2홉, 다단계 추론)
    #
    # infer_at_depth=1 (기본값): depth ≥ 1 → root에서도 탐색
    # infer_at_depth=2          : depth ≥ 2 → 2홉 이상에서만 탐색
    #   → Meeting→Decision 은 User→Meeting 을 거쳐야만 로드됨
    #   → User를 seed로 바로 fetch 시 Decision을 건너뜀 (데이터 폭발 방지)
    infer_at_depth: int = field(default=1)

    # ── weight ──────────────────────────────────────────────────── 
    # 같은 depth에서 여러 관계를 탐색할 때의 우선순위 가중치.
    # traverser가 weight 내림차순으로 관계를 정렬해 처리한다.
    #
    # 높을수록 컨텍스트 앞부분에 위치 → LLM이 먼저 읽음. 
    #
    # 현재는 정적(static) 가중치 — 관계 종류별 고정값.
    # 향후 질문 임베딩 기반 동적 가중치로 확장 가능:
    #   weight_fn: Callable[[str], float] = None  # question → weight
    weight: float = field(default=1.0)


# ──────────────────────────────────────────────────────────────────
# LLM Structured Output 스키마
#
# build_ontology_context에서 llm.with_structured_output()에 전달.
# LLM이 질문에서 추출해야 할 정보의 형태를 Pydantic으로 강제한다.
# ──────────────────────────────────────────────────────────────────

# workspace_categories 허용값 — 이 8개 외 값은 Pydantic이 자동 차단
WsCategoryLiteral = Literal[
    "WS_MEMBERS",
    "WS_DEPARTMENTS",
    "WS_REPORTS",
    "WS_SCHEDULE",
    "WS_DEVICE",
    "WS_INTEGRATION",
    "WS_TASKS",
    "WS_DECISIONS",
]


class ExtractedEntity(BaseModel):
    name: str
    type: Literal["User", "Meeting"]  # 이 두 값만 허용


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]                    # 질문에 언급된 사람/회의 이름
    workspace_categories: list[WsCategoryLiteral]      # 관련 워크스페이스 집합 카테고리
    date_from: str | None                              # YYYY-MM-DD 또는 None
    date_to: str | None