# [SCN-XXX] 시나리오 제목

## 1. 개요

- **의도:** 사용자가 무엇을 원하는가?
- **트리거 발화:** 어떤 말을 했을 때 이 시나리오가 시작되는가?

## 2. 그래프 흐름도 (Path)

`Node A` -> `Node B` -> `Node C` -> `End`

## 3. 단계별 데이터 변화 (State Transition)

| 순서 | 실행 노드  | Input (필요한 데이터) | Output (업데이트할 데이터)      |
| :--- | :--------- | :-------------------- | :------------------------------ |
| 1    | Scribe     | 오디오 스트림         | `transcript`                    |
| 2    | Supervisor | `transcript`          | `next_node`, `current_scenario` |
| 3    | ...        | ...                   | ...                             |

## 4. 테스트용 Mock 데이터 (JSON)

- `tests/mocks/SCN-XXX_input.json` 참조
