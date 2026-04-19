# Slack 클라이언트 API 명세

**위치:** `app/infra/clients/slack.py`  
**클래스:** `SlackClient(BaseClient)`  
**버전:** 1.0.0

---

## 개요

WorkB 서비스에서 Slack Bot API를 직접 호출하는 클라이언트.  
`integrations` 테이블에 저장된 `bot_token`을 사용하며, 모든 메서드는 `async`로 동작한다.

Slack API는 HTTP 200이어도 `ok: false`로 실패를 반환하므로,  
모든 응답은 `_check_slack_error()`를 통해 검증되고 실패 시 `ValueError`를 발생시킨다.

---

## OAuth 스코프

| 스코프 | 용도 |
|--------|------|
| `chat:write` | 봇이 참여한 채널에 메시지 전송 |
| `chat:write.public` | 봇 미참여 공개 채널에도 전송 가능 |
| `channels:read` | 공개 채널 목록 및 멤버 조회 |
| `channels:join` | 봇을 채널 멤버로 자동 참여 |
| `users:read` | 유저 이름 등 기본 정보 조회 |
| `users:read.email` | 유저 이메일 조회 |
| `im:write` | DM 채널 생성 |
| `pins:write` | 메시지 핀 고정 |
| `files:write` | 파일 업로드 (미구현 — KAN-166) |

> 스코프 추가 후 반드시 워크스페이스 재연동 필요

---

## 초기화

```python
from app.infra.clients.slack import SlackClient
from app.domains.integration.repository import get_integration
from app.domains.integration.models import ServiceType

integration = get_integration(db, workspace_id, ServiceType.slack)
if not integration or not integration.access_token:
    raise ValueError("Slack 연동이 필요합니다.")

slack = SlackClient(bot_token=integration.access_token)
```

---

## 메서드 명세

---

### get_public_channels

드롭다운용 공개 채널 목록 조회

**시그니처**

```python
async def get_public_channels() -> List[Dict[str, str]]
```

**파라미터:** 없음

**반환값**

```python
[
    {"id": "C1234567", "name": "general"},
    {"id": "C7654321", "name": "random"},
]
```

**예외**

| 조건 | 에러 |
|------|------|
| 토큰 권한 없음 | `ValueError: Slack API Error: not_authed` |

**Slack API:** `GET /conversations.list`  
**스코프:** `channels:read`

**사용 예시**

```python
channels = await slack.get_public_channels()
# 프론트 드롭다운에 전달
```

---

### send_message

채널에 텍스트 또는 Block Kit 메시지 전송

**시그니처**

```python
async def send_message(
    channel_id: str,
    text: str,
    blocks: Optional[List[Dict]] = None,
    thread_ts: Optional[str] = None,
) -> Dict[str, Any]
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID (예: `C1234567`) |
| `text` | `str` | ✅ | 메시지 본문. blocks 사용 시 fallback 텍스트로 쓰임 |
| `blocks` | `List[Dict]` | ❌ | Block Kit 블록 리스트 |
| `thread_ts` | `str` | ❌ | 스레드로 달 경우 부모 메시지의 ts |

**반환값**

```python
{"ok": True, "ts": "1716300000.123456", ...}
```

**예외**

| 조건 | 에러 |
|------|------|
| 존재하지 않는 채널 | `ValueError: Slack API Error: channel_not_found` |
| 채널 접근 권한 없음 | `ValueError: Slack API Error: not_in_channel` |

**Slack API:** `POST /chat.postMessage`  
**스코프:** `chat:write`, `chat:write.public`

**사용 예시**

```python
# 기본 메시지
result = await slack.send_message(channel_id="C1234567", text="회의가 시작됩니다.")

# 스레드 답글
await slack.send_message(
    channel_id="C1234567",
    text="WBS 목록",
    thread_ts="1716300000.123456"
)
```

---

### send_minutes

회의록을 Block Kit 형식으로 채널에 전송. 이후 스레드 연결에 사용할 `ts` 반환.

**시그니처**

```python
async def send_minutes(
    channel_id: str,
    meeting_title: str,
    minutes_text: str,
    action_items: Optional[List[str]] = None,
    link_url: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> str
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |
| `meeting_title` | `str` | ✅ | 회의 제목 (헤더에 표시) |
| `minutes_text` | `str` | ✅ | 회의록 본문. 3000자 초과 시 자동 truncate |
| `action_items` | `List[str]` | ❌ | 액션아이템 문자열 리스트. 전달 시 별도 섹션으로 추가 |
| `link_url` | `str` | ❌ | WorkB 회의록 페이지 URL. 전달 시 버튼 추가 |
| `thread_ts` | `str` | ❌ | 기존 스레드에 답글로 달 경우 |

**반환값**

```python
"1716300000.123456"  # 전송된 메시지의 ts (스레드 기준점으로 사용)
```

**예외**

| 조건 | 에러 |
|------|------|
| 채널 없음 / 권한 없음 | `ValueError: Slack API Error: channel_not_found` |

**Slack API:** `POST /chat.postMessage` (내부적으로 `send_message` 호출)  
**스코프:** `chat:write`, `chat:write.public`

**사용 예시**

```python
ts = await slack.send_minutes(
    channel_id="C1234567",
    meeting_title="4월 스프린트 회의",
    minutes_text="오늘 회의에서 A, B, C를 논의했습니다.",
    action_items=["API 문서 작성", "코드 리뷰"],
    link_url="https://workb.app/meetings/1/minutes"
)
# ts를 이후 스레드 연결에 사용
```

---

### join_channel

봇을 채널 멤버로 참여시킴. `pin_message` 전에 반드시 호출.

**시그니처**

```python
async def join_channel(channel_id: str) -> None
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |

**반환값:** 없음

**예외**

| 조건 | 에러 |
|------|------|
| 비공개 채널 | `ValueError: Slack API Error: not_allowed_token_type` |
| 스코프 없음 | `ValueError: Slack API Error: missing_scope` |

**Slack API:** `POST /conversations.join`  
**스코프:** `channels:join`

**사용 예시**

```python
await slack.join_channel(channel_id="C1234567")
await slack.pin_message(channel_id="C1234567", message_ts=ts)
```

---

### pin_message

메시지를 채널 상단에 핀 고정. 반드시 `join_channel` 후 호출.

**시그니처**

```python
async def pin_message(channel_id: str, message_ts: str) -> None
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |
| `message_ts` | `str` | ✅ | 핀 고정할 메시지의 ts |

**반환값:** 없음

**예외**

| 조건 | 에러 |
|------|------|
| 봇이 채널 멤버가 아님 | `ValueError: Slack API Error: not_in_channel` |
| 스코프 없음 | `ValueError: Slack API Error: missing_scope` |

**Slack API:** `POST /pins.add`  
**스코프:** `pins:write`, `channels:join`

---

### send_action_items

액션아이템을 회의록 스레드에 멘션하고 각 담당자에게 DM 전송.

**시그니처**

```python
async def send_action_items(
    channel_id: str,
    thread_ts: str,
    action_items: List[Dict[str, str]],
) -> None
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |
| `thread_ts` | `str` | ✅ | `send_minutes()`가 반환한 ts |
| `action_items` | `List[Dict]` | ✅ | 아래 형식 참고 |

`action_items` 항목 형식

| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `slack_user_id` | `str` | ✅ | Slack user ID (U로 시작) |
| `task` | `str` | ✅ | 태스크 내용 |
| `due` | `str` | ❌ | 기한. 없으면 "미정" 표시 |

> `slack_user_id`는 WorkB DB의 `users.email`로 `get_user_info()`를 호출해 미리 조회해야 함

**반환값:** 없음

**동작 순서**

1. 스레드에 `@slack_user_id 태스크명 (기한: ...)` 멘션
2. 담당자에게 DM으로 태스크 내용 재전달

**Slack API:** `POST /chat.postMessage` × N, `POST /conversations.open` × N  
**스코프:** `chat:write`, `chat:write.public`, `im:write`

**사용 예시**

```python
await slack.send_action_items(
    channel_id="C1234567",
    thread_ts="1716300000.123456",
    action_items=[
        {"slack_user_id": "U1234567", "task": "로그인 기능 구현", "due": "5/10"},
        {"slack_user_id": "U7654321", "task": "API 문서 작성"},
    ]
)
```

---

### get_channel_members

채널에 속한 멤버 user_id 목록 반환.

**시그니처**

```python
async def get_channel_members(channel_id: str) -> List[str]
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |

**반환값**

```python
["U1234567", "U7654321", "U0000001"]
```

**Slack API:** `GET /conversations.members`  
**스코프:** `channels:read`

---

### get_user_info

Slack user_id로 이름·이메일 조회. WorkB 계정 매핑에 사용.

**시그니처**

```python
async def get_user_info(user_id: str) -> Dict[str, Any]
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | `str` | ✅ | Slack user ID (U로 시작) |

**반환값**

```python
{
    "id": "U1234567",
    "name": "홍길동",
    "email": "hong@company.com"  # 이메일 미설정 시 빈 문자열
}
```

**예외**

| 조건 | 에러 |
|------|------|
| 존재하지 않는 user_id | `ValueError: Slack API Error: user_not_found` |

**Slack API:** `GET /users.info`  
**스코프:** `users:read`, `users:read.email`

---

### open_dm

user_id로 DM 채널을 열고 채널 ID 반환. 이미 열려있으면 기존 채널 ID 반환.

**시그니처**

```python
async def open_dm(user_id: str) -> str
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | `str` | ✅ | Slack user ID |

**반환값**

```python
"D1234567"  # DM 채널 ID
```

**예외**

| 조건 | 에러 |
|------|------|
| 봇에게 DM 시도 | `ValueError: Slack API Error: cannot_dm_bot` |

**Slack API:** `POST /conversations.open`  
**스코프:** `im:write`

---

### send_dm_to_workspace_member

WorkB 이메일로 채널 멤버를 역탐색 후 DM 전송.

**시그니처**

```python
async def send_dm_to_workspace_member(
    channel_id: str,
    workb_email: str,
    text: str,
) -> Dict[str, Any]
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 멤버를 탐색할 채널 ID |
| `workb_email` | `str` | ✅ | WorkB DB의 `users.email` |
| `text` | `str` | ✅ | DM 내용 |

**반환값:** `send_message()` 반환값과 동일

**예외**

| 조건 | 에러 |
|------|------|
| 채널에 해당 이메일 없음 | `ValueError: 채널에서 {email} 유저를 찾을 수 없습니다.` |

**내부 동작 순서**

1. `get_channel_members()` — 채널 멤버 전체 조회
2. `get_user_info()` — 이메일 일치하는 user_id 탐색 (첫 매칭에서 중단)
3. `open_dm()` → `send_message()` — DM 전송

**스코프:** `channels:read`, `users:read`, `users:read.email`, `im:write`, `chat:write`

> 멤버가 많은 채널에서 이메일 탐색이 느릴 수 있음.  
> 가능하면 `slack_user_id`를 미리 확보해 `open_dm`을 직접 호출할 것.

---

### schedule_message

지정 시각에 메시지 예약 전송.

**시그니처**

```python
async def schedule_message(
    channel_id: str,
    text: str,
    post_at: int,
) -> str
```

**파라미터**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `channel_id` | `str` | ✅ | 채널 ID |
| `text` | `str` | ✅ | 예약 메시지 내용 |
| `post_at` | `int` | ✅ | 전송 시각 (Unix timestamp, 초 단위). 현재 시각 기준 최소 60초 이후 |

**반환값**

```python
"Q0ATDSEMAT1"  # scheduled_message_id (예약 취소 시 사용)
```

**예외**

| 조건 | 에러 |
|------|------|
| `post_at`이 60초 미만 | `ValueError: Slack API Error: time_in_past` |

**Slack API:** `POST /chat.scheduleMessage`  
**스코프:** `chat:write`

**사용 예시**

```python
import time

scheduled_id = await slack.schedule_message(
    channel_id="C1234567",
    text="10분 후 회의가 시작됩니다.",
    post_at=int(time.time()) + 600
)
```

---

## export_slack 전체 흐름

```
POST /actions/meetings/{id}/export/slack
  │  BackgroundTasks로 즉시 {"status": "processing"} 반환
  │
  ├─ 1. integrations 테이블 → bot_token, channel_id 조회
  │
  ├─ 2. join_channel(channel_id)
  │       스코프: channels:join
  │
  ├─ 3. ts = send_minutes(channel_id, title, minutes_text, action_items, link_url)
  │       스코프: chat:write.public
  │
  ├─ 4. pin_message(channel_id, ts)
  │       스코프: pins:write
  │
  └─ 5. send_action_items(channel_id, ts, action_items)  — slack_action_items 있을 때만
          ├─ send_message(thread_ts=ts)     스코프: chat:write.public  (멘션)
          └─ open_dm → send_message         스코프: im:write           (DM)
```

---

## 에러 처리 패턴

`export_slack`은 BackgroundTask로 실행되므로 에러가 router로 전파되지 않는다.
내부 try/except로 모든 에러를 잡아 logger.error로 기록한다.

```python
# services/slack.py
try:
    ...
except Exception as e:
    logger.error(f"[Slack Export] 실패 - meeting_id={meeting_id} : {e}")
```

채널 목록 조회 등 동기 API는 `ValueError`를 router에서 변환한다.

```python
# integration/router.py
try:
    channels = await service.get_slack_channel(db, workspace_id)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

---

## 미구현 — upload_file

| 항목 | 내용 |
|------|------|
| **용도** | 보고서(xlsx/pptx) 파일을 채널에 업로드 |
| **Slack API** | `POST /files.getUploadURLExternal` → `PUT {upload_url}` → `POST /files.completeUploadExternal` |
| **스코프** | `files:write` |
| **미구현 이유** | KAN-165 보고서 생성이 선행되어야 함 |
| **구현 티켓** | KAN-166 |
