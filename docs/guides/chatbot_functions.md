# 챗봇 호출 가능 함수 목록

> 팀원 D(챗봇)는 HTTP 엔드포인트를 거치지 않고 `action/service.py` 함수를 직접 import해서 호출합니다.
> Request 객체 의존 없이 `(db, workspace_id, meeting_id, ...)` 형태로 통일되어 있습니다.

```python
from app.domains.action.service import (
    export_slack,
    export_notion,
    export_jira,
    export_kakao,
    export_google_calendar,
    suggest_next_meeting,
    register_next_meeting,
)
```

---

## export_slack

회의록·액션아이템을 Slack 채널로 전송합니다.

```python
await export_slack(
    db=db,
    workspace_id=1,
    meeting_id=meeting_id,
    channel_id=None,           # 생략 시 integrations.extra_config.channel_id 사용
    include_action_items=True, # 기본값 True
)
```

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `db` | Session | ✅ | DB 세션 |
| `workspace_id` | int | ✅ | 워크스페이스 ID |
| `meeting_id` | int | ✅ | 회의 ID |
| `channel_id` | str | ❌ | 생략 시 저장된 기본 채널 사용 |
| `include_action_items` | bool | ❌ | 액션아이템 포함 여부 (기본 True) |

**동작 순서:**
1. Slack 연동 토큰 조회
2. 채널 참여 (`join_channel`)
3. 회의록 Block Kit 전송 → `ts` 반환
4. 메시지 핀 고정
5. 액션아이템 있으면 스레드 멘션 + 담당자 DM

**예외:** `ValueError` — 연동 없음 / 채널 미설정 / 회의 없음 / 회의록 없음

---

## export_notion

> ⏳ 미구현 (KAN-166 진행 예정)

```python
await export_notion(db=db, workspace_id=1, meeting_id=meeting_id)
```

---

## export_jira

> ⏳ 미구현 (KAN-166 진행 예정)

```python
await export_jira(db=db, workspace_id=1, meeting_id=meeting_id)
```

---

## export_kakao

> ⏳ 미구현 (KAN-166 진행 예정)

```python
await export_kakao(db=db, workspace_id=1, meeting_id=meeting_id)
```

---

## export_google_calendar

> ⏳ 미구현 (KAN-166 진행 예정)

```python
await export_google_calendar(db=db, workspace_id=1, meeting_id=meeting_id)
```

---

## suggest_next_meeting

> ⏳ 미구현 (KAN-166 진행 예정)

Freebusy API + LLM으로 참석자 빈 시간 3개 추천합니다.

```python
slots = await suggest_next_meeting(
    db=db,
    workspace_id=1,
    meeting_id=meeting_id,
    attendee_emails=["a@company.com", "b@company.com"],
)
# 반환: ["2026-05-01T10:00:00", "2026-05-02T14:00:00", ...]
```

---

## register_next_meeting

> ⏳ 미구현 (KAN-166 진행 예정)

Google Calendar에 다음 회의 일정을 등록합니다.

```python
await register_next_meeting(
    db=db,
    workspace_id=1,
    meeting_id=meeting_id,
    title="2차 스프린트 회의",
    scheduled_at="2026-05-01T10:00:00",
)
```

---

## 사용 예시 (챗봇 시나리오)

```python
# "AA 회의록 슬랙으로 보내줘"
await export_slack(db=db, workspace_id=workspace_id, meeting_id=meeting_id)

# "노션에도 저장해줘"
await export_notion(db=db, workspace_id=workspace_id, meeting_id=meeting_id)

# "다음 회의 언제가 좋을까?"
slots = await suggest_next_meeting(
    db=db,
    workspace_id=workspace_id,
    meeting_id=meeting_id,
    attendee_emails=attendee_emails,
)
```
