# SharedState 구조 정의

> `app/core/graph/state.py`의 TypedDict 각 Key별 실제 데이터 구조
> LangGraph 노드(service.py)에서 read/write 시 이 형식을 따른다

---

## 팀원 E Write 가능 Key

---

### `wbs` — `List[dict]`

> 회의 종료 후 LLM이 생성한 WBS 에픽·태스크 목록

```python
wbs = [
    {
        "epic_id": 1,                    # DB wbs_epics.id (저장 후 채워짐)
        "title": "인증 시스템 구축",
        "order_index": 0,
        "jira_epic_id": None,            # JIRA 동기화 후 채워짐
        "tasks": [
            {
                "task_id": 1,            # DB wbs_tasks.id (저장 후 채워짐)
                "title": "로그인 API 개발",
                "assignee_id": 3,        # users.id (None 가능)
                "priority": "high",      # low | medium | high | critical
                "due_date": "2025-04-30", # None 가능
                "progress": 0,           # 0~100
                "status": "todo",        # todo | in_progress | done
                "jira_issue_id": None    # JIRA 동기화 후 채워짐
            }
        ]
    }
]
```

---

### `realtime_actions` — `List[dict]`

> 회의 중 실시간 감지된 액션 아이템 (STT transcript 기반)

```python
realtime_actions = [
    {
        "content": "다음 주까지 API 문서 작성",
        "assignee_id": 3,                # users.id (감지된 담당자, None 가능)
        "due_date": "2025-04-21",        # 감지된 기한 (None 가능)
        "detected_at": "2025-04-14T10:30:00",
        "status": "pending"              # pending | in_progress | done
    }
]
```

---

### `external_links` — `dict`

> 외부 API 호출 결과로 생성된 링크·ID 모음
> 서비스별 키가 없으면 해당 서비스 미연동 또는 미호출 상태

```python
external_links = {
    "jira": {
        "epic_url": "https://company.atlassian.net/browse/EPIC-1",
        "issue_urls": [
            "https://company.atlassian.net/browse/TASK-1",
            "https://company.atlassian.net/browse/TASK-2"
        ]
    },
    "google_calendar": {
        "event_id": "abc123xyz",
        "event_url": "https://calendar.google.com/event?eid=abc123"
    },
    "notion": {
        "page_id": "notion-page-uuid",
        "page_url": "https://notion.so/abc123"
    },
    "slack": {
        "channel_id": "C1234567",
        "message_ts": "1713234567.000100"   # Slack 메시지 타임스탬프
    }
}
```

---

### `integration_settings` — `dict`

> 각 서비스의 연동 상태 + n8n webhook_url
> 회의 시작 시 service.py가 DB `integrations` 테이블에서 로드하여 state에 올림
>
> **webhook_url 구조:**
> `{n8n_base_url}/webhook/{서비스}-ws{workspace_id}`
> 예: `http://localhost:5678/webhook/google-calendar-ws1`
> 어드민이 n8n 서버 주소만 입력하면 백엔드가 자동 조합

```python
integration_settings = {
    "jira": {
        "is_connected": True,
        "webhook_url": "http://localhost:5678/webhook/jira-ws1"
    },
    "slack": {
        "is_connected": True,
        "webhook_url": "http://localhost:5678/webhook/slack-ws1"
    },
    "notion": {
        "is_connected": False,
        "webhook_url": None
    },
    "google_calendar": {
        "is_connected": True,
        "webhook_url": "http://localhost:5678/webhook/google-calendar-ws1"
    },
    "kakao": {
        "is_connected": False,
        "webhook_url": None
    }
}
```

---

## 전체 Key 소유권

| Key | 타입 | Write 담당 | 시점 |
|-----|------|-----------|------|
| `next_node` | `str` | supervisor | 매 노드 전환 시 |
| `transcript` | `List[dict]` | 팀원 C (meeting) | 회의 중 실시간 |
| `agenda` | `List[dict]` | 팀원 B (meeting) | 회의 전 |
| `search_query` | `str` | 팀원 D (knowledge) | 챗봇 검색 시 |
| `retrieved_docs` | `List[dict]` | 팀원 D (knowledge) | RAG 검색 후 |
| `chat_history` | `List[dict]` | 팀원 D (knowledge) | 챗봇 대화 중 |
| `summary` | `str` | 팀원 D (intelligence) | 회의 종료 후 |
| `decisions` | `List[str]` | 팀원 D (intelligence) | 회의 종료 후 |
| `screenshot_analysis` | `str` | 팀원 D (vision) | 화면 공유 분석 후 |
| **`wbs`** | `List[dict]` | **팀원 E (action)** | 회의 종료 후 |
| **`realtime_actions`** | `List[dict]` | **팀원 E (action)** | 회의 중 실시간 |
| **`external_links`** | `dict` | **팀원 E (action)** | 외부 API 호출 후 |
| **`integration_settings`** | `dict` | **팀원 E (integration)** | 회의 시작 시 |
| `accuracy_score` | `float` | quality | 품질 검증 후 |
| `errors` | `List[str]` | 전 도메인 | 에러 발생 시 |
