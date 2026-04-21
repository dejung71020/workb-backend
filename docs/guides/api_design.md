# API 설계 결정 기록

WorkB 백엔드 API 설계 시 RESTful 근거와 결정 이유를 누적 기록한다.

---

## 1. action 도메인 엔드포인트 구조

**결정:** `POST /api/v1/actions/meetings/{meeting_id}/export/slack`

**대안 검토:**

| 후보 경로 | 탈락 이유 |
|-----------|-----------|
| `/meetings/{meeting_id}/export/slack` | meeting 도메인 router에 export 코드가 붙어야 함 → 팀원 B(meeting 담당)와 팀원 E(action 담당) 코드 충돌 |
| `/actions/export/slack?meeting_id={id}` | export 대상(회의)이 URL에 드러나지 않아 가독성 낮음 |

**채택 이유:**
- action 도메인과 meeting 도메인의 코드 소유권 분리
- `meeting_id`를 path parameter로 두어 "어떤 회의의 결과물을 내보내는지" URL에서 명확히 표현
- RESTful 원칙: 하위 리소스에 대한 행위는 상위 리소스 ID를 path에 포함

---

## 2. `meeting_id` — path parameter vs query parameter

**결정:** path parameter (`/meetings/{meeting_id}`)

**채택 이유:**
- export는 특정 회의 리소스에 종속된 행위
- RESTful 원칙: 리소스 식별자는 path, 필터/옵션은 query parameter
- `meeting_id`가 없으면 요청 자체가 성립되지 않는 필수값 → path가 적절

---

## 3. `workspace_id` — path 미포함

**결정:** path에 포함하지 않음. 현재는 하드코딩(=1), 추후 auth context(JWT)에서 추출

**채택 이유:**
- workspace는 인증된 사용자의 컨텍스트에서 결정되는 값
- URL에 노출할 필요 없음 (보안 + 간결성)
- `meeting_id`로 DB에서 `meeting.workspace_id`를 조회하면 충분

---

## 4. Fire and Forget 패턴 — 즉시 `{"status": "processing"}` 반환

**결정:** export 엔드포인트는 BackgroundTasks로 비동기 처리 후 즉시 응답

**채택 이유:**
- Slack/Notion/JIRA 등 외부 API 호출은 수 초 소요 가능
- 사용자가 응답을 기다리지 않아도 됨
- RESTful 관점: 202 Accepted 패턴 (요청은 수락됐으나 처리는 비동기)

```python
@router.post("/export/slack", response_model=ExportResponse)
async def export_to_slack(..., background_tasks: BackgroundTasks):
    background_tasks.add_task(export_slack, ...)
    return ExportResponse()  # {"status": "processing"}
```

---

## 5. action 도메인 내부 구조 분리

**결정:**

```
action/
  schemas.py       ← 전체 스키마 (서비스별 섹션 구분)
  service.py       ← chatbot 진입점 (re-export만)
  router.py        ← 라우터 진입점 (sub-router include)
  services/        ← 서비스별 구현 분리
  routers/         ← 서비스별 라우터 분리
```

**채택 이유:**
- 각 export 함수가 DB 조회 + API 호출로 40~60줄 예상 → 5개 합치면 300줄 이상
- `service.py`는 챗봇 import 경로(`from app.domains.action.service import export_slack`) 유지를 위해 re-export 진입점으로만 사용
- `schemas.py`는 스키마가 짧아 단일 파일로 충분

---

## 6. router tags 위치

**결정:** tags는 `api_router.py`의 include 시점에만 지정, 각 도메인 router에는 미지정

**채택 이유:**
- 도메인 router와 api_router.py 양쪽에 tags를 지정하면 Swagger에서 두 태그가 합산됨
- 기존 integration_router 패턴과 일관성 유지

---

## 7. IntegrationResponse에 selected_channel_id 추가

**결정:** `IntegrationResponse`에 `selected_channel_id: Optional[str]` 필드 추가

**배경:**
- Slack 연동 후 기본 채널을 선택하면 `integrations.extra_config.channel_id`에 저장됨
- 프론트엔드 드롭다운이 페이지 새로고침 시 항상 "채널 선택"으로 초기화되는 UX 문제 발생
- `IntegrationResponse`가 `extra_config`를 노출하지 않아 프론트에서 저장된 채널을 알 수 없음

**채택 이유:**
- `extra_config` 전체를 노출하면 불필요한 내부 데이터(team_id 등)가 노출됨
- Slack에 필요한 값(channel_id)만 별도 필드로 추출해 응답에 포함하는 것이 적절
- 다른 서비스 연동 시에도 동일 패턴 적용 가능 (notion의 workspace_name 등)

```python
# schemas.py
class IntegrationResponse(BaseModel):
    id: int
    service: ServiceType
    is_connected: bool
    updated_at: datetime
    selected_channel_id: Optional[str] = None  # extra_config.channel_id 추출

# router.py
IntegrationResponse(
    ...
    selected_channel_id=item.extra_config.get("channel_id") if item.extra_config else None,
)
```

---

## 8. export_slack — BackgroundTasks (Fire and Forget)

**결정:** 에러를 router로 전파하지 않고 logger.error로만 기록

**채택 이유:**
- BackgroundTask는 이미 응답이 반환된 후 실행되므로 router에서 에러를 잡을 수 없음
- 외부 API 장애가 서버 에러(500)로 노출되지 않아야 함
- 에러 발생 시 로그로 추적, 향후 알림 시스템(Slack 에러 채널) 연동 가능
