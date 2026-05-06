from __future__ import annotations
from app.core.ontology.schema import EntityType, Relation
from app.core.ontology.fetchers import ONTOLOGY
from app.infra.database.session import SessionLocal


def _resolve_entity_id(
    entity_type: EntityType, name: str, workspace_id: int
) -> int | None:
    """
    엔티티 이름(name) -> PK(id) 해소.
    LLM이 추출한 "박민준" 같은 이름을 실제 user.id로 변환한다.
    이름을 PK로 바꿔야 fetch_fn에 넘길 수 있기 때문에 필요하다.
    """
    from app.domains.user.models import User
    from app.domains.meeting.models import Meeting

    db = SessionLocal()
    try:
        if entity_type == EntityType.USER:
            row = db.query(User.id).filter(User.name.ilike(f"%{name}%")).first()
            return row.id if row else None

        if entity_type == EntityType.MEETING:
            row = (
                db.query(Meeting.id)
                .filter(
                    Meeting.title.ilike(f"%{name}%"),
                    Meeting.workspace_id == workspace_id,
                )
                .order_by(Meeting.scheduled_at.desc())
                .first()
            )
            return row.id if row else None

    except Exception:
        return None
    finally:
        db.close()


class OntologyTraverser:
    """
    지식 그래프 탐색기.

    seed 엔티티(들)에서 출발해 ONTOLOGY에 정의된 관계를 따라
    최대 max_depth 홉(hop)까지 관련 데이터를 자동으로 수집한다.

    핵심 알고리즘:
    1. seed 엔티티를 큐에 넣는다.
    2. 현재 엔티티 타입에서 출발하는 관계를 ONTOLOGY에서 찾는다.
    3. 관계를 weight 내림차순으로 정렬 (중요한 관계를 먼저 처리)
    4. infer_at_depth > current_depth 조건을 만족하는 관계만 탐색
        -> depth=1 에서 infer_at_depth=2 관계는 건너뜀 (데이터 폭발 방지).
    5. fetch_fn(entity_id, workspace_id, ctx)를 호출해 연결된 데이터 수집.
    6. 수집된 데이터를 새 엔티티로 간주해 큐에 추가.
    7. visited 셋으로 순환 참조 (A->B->A->...) 방지.
    8. 수집된 추론 결과를 root 엔티티의 "_inferred" 딕셔너리에 누적.

    결과 그래프 구조:
    [
        {
            "id": 42,
            "type": "User",
            "name": "박민준",
            "_relations": {                         ← depth=1 직접 관계
                "사용자가 참여한 회의": [...meetings],
                "사용자에게 할당된 태스크": [...tasks],
            },
            "_inferred": {                          ← depth=2 추론 관계
                "회의에서 나온 결정 사항 (via 사용자가 참여한 회의)": [...decisions],
            }
        },
        ...
    ]
    """

    def __init__(self, max_depth: int = 2):
        # max_depth: 탐색할 최대 홉 수, 2면 seed->이웃->이웃까지,
        self.max_depth = max_depth

    def traverse(
        self,
        seed_entities: list[dict],
        workspace_id: int,
    ) -> list[dict]:
        """
        seed_entities: [{"id": int, "type": EntityType.value, "name": str, "ctx": dict}, ...]
            - id    : 엔티티 PK (None이면 name으로 해소 시도)
            - type  : EntityType enum 값 (str)
            - name  : 엔티티 이름 (id 해소 실패 시 로그용)
            - ctx   : {"date_from": ..., "date_to": ...} 날짜 필터

        반환: root 엔티티에 _relations, _inferred 가 채워진 리스트
        """
        result = []

        for seed in seed_entities:
            entity_id = seed.get("id")
            entity_type = seed.get("type")
            ctx = seed.get("ctx") or {}

            # id가 없으면 이름으로 DB 해소 시도
            if not entity_id and seed.get("name"):
                entity_id = _resolve_entity_id(
                    EntityType(entity_type),
                    seed["name"],
                    workspace_id,
                )
            if not entity_id:
                continue  # 해소 실패 - 이 seed는 건너뜀

            root = {**seed, "id": entity_id, "_relations": {}, "_inferred": {}}

            # visited: (entity_type, entity_id) 쌍의 frozenset
            # 순환 참조를 막기 위해 이미 방문한 노드는 건너뜀
            visited: set[tuple] = {(entity_type, entity_id)}

            self._explore(
                entity=root,
                workspace_id=workspace_id,
                depth=1,  # root 자신은 depth=0, 첫 탐색은 depth=1
                visited=visited,
                ctx=ctx,
                root=root,  # 추론 결과를 root._inferred 에 직접 누적
                via_description=None,
                via_relation=None,
            )
            result.append(root)

        return result

    def _explore(
        self,
        entity: dict,
        workspace_id: int,
        depth: int,
        visited: set,
        ctx: dict,
        root: dict,
        via_description: str | None,
        via_relation: str | None,
    ) -> None:
        if depth > self.max_depth:
            return

        # 이 엔티티 타입에서 출발하는 관계 목록
        relations: list[Relation] = [
            r
            for r in ONTOLOGY
            if r.from_entity.value == entity["type"]
            # infer_at_depth > depth: "이 관계는 depth 이후에만 탐색"
            # 예) infer_at_depth=2, depth=1 → 1 < 2 이므로 탐색 안 함
            #     infer_at_depth=2, depth=2 → 2 >= 2 이므로 탐색 허용
            and r.infer_at_depth <= depth
        ]

        # ── weight 내림차순 정렬 ──────────────────────────────────
        # 같은 depth에서 중요한 관계를 먼저 탐색 → 컨텍스트 앞부분 확보
        # 예) User에서 depth=1 탐색 시:
        #   ASSIGNED_TO(1.8) → PARTICIPATED_IN(1.5) → BELONGS_TO(1.0) 순
        relations.sort(key=lambda r: r.weight, reverse=True)

        for relation in relations:
            # fetch_fn 호출: 연결된 엔티티 목록 가져오기
            try:
                children = relation.fetch_fn(entity["id"], workspace_id, ctx)
            except Exception:
                children = []

            if not children:
                continue

            # 결과를 어디에 저장할지 결정
            if depth == 1:
                # depth=1: 직접 연결 → root._relation
                root["_relations"][relation.description] = children
                target_dict = root["_relations"]
            else:
                # depth=2 이상: 추론 결과 -> root._inferred
                # "사용자가 참여한 회의의 결정 사항" 형태의 복합 설명 생성
                inferred_key = (
                    f"{relation.description} (via {via_description})"
                    if via_description
                    else relation.description
                )
                # 중복 id 제거: 여러 경로로 같은 Decision이 나올 수 있음
                existing = {
                    item["id"] for item in root["_inferred"].get(inferred_key, [])
                }
                new_items = [c for c in children if c.get("id") not in existing]
                if new_items:
                    root["_inferred"].setdefault(inferred_key, []).extend(new_items)
                target_dict = root["_inferred"]

            # 다음 depth 탐색: children 각각을 새 출발점으로
            for child in children:
                child_key = (child.get("type"), child.get("id"))
                if child_key in visited:
                    continue
                visited.add(child_key)

                self._explore(
                    entity=child,
                    workspace_id=workspace_id,
                    depth=depth + 1,
                    visited=visited,
                    ctx=ctx,
                    root=root,
                    # via_description: 다음 레벨에서 "~via~" 설명에 사용
                    via_description=relation.description,
                    via_relation=relation.type.value,
                )
