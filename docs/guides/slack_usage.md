# SlackClient 사용 가이드

> `app/infra/clients/slack.py`
> Slack 연동이 완료된 워크스페이스에서 사용 가능합니다.

---

## 클라이언트 초기화

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

## 1. 채널에 메시지 전송

```python
await slack.send_message(
    channel_id="C1234567",
    text="회의가 시작되었습니다."
)
```

---

## 2. 채널에 회의록 전송 + 스레드 활용

> `send_minutes`는 전송된 메시지의 `ts`(타임스탬프 ID)를 반환합니다.
> 이후 WBS·액션아이템을 스레드로 달 때 `thread_ts`로 사용합니다.

```python
# 회의록 전송 → ts 반환
ts = await slack.send_minutes(
    channel_id="C1234567",
    meeting_title="4월 스프린트 회의",
    minutes_text="오늘 회의에서는 A, B, C를 논의했습니다.",
    action_items=["API 문서 작성", "리뷰 요청"],        # 선택
    link_url="https://workb.app/meetings/1/minutes"    # 선택
)
# ts = "1716300000.123456"

# WBS를 스레드 답글로 전송
await slack.send_message(
    channel_id="C1234567",
    text="WBS 태스크 목록...",
    thread_ts=ts
)
```

---

## 3. 채널 참여 (핀 고정 전 필수)

> `pins:write`는 봇이 채널 멤버여야 동작합니다.
> `pin_message` 전에 반드시 호출하세요.

```python
await slack.join_channel(channel_id="C1234567")
```

---

## 4. 핀 고정

```python
await slack.join_channel(channel_id="C1234567")   # 멤버 아닐 경우 필요
ts = await slack.send_minutes(channel_id, "회의 제목", minutes_text)
await slack.pin_message(channel_id=channel_id, message_ts=ts)
```

---

## 5. 액션아이템 스레드 멘션 + 담당자 DM

> `slack_user_id`는 `get_user_info()`로 미리 조회해야 합니다.
> `due` 없으면 "미정"으로 표시됩니다.

```python
await slack.send_action_items(
    channel_id="C1234567",
    thread_ts=ts,    # send_minutes()가 반환한 ts
    action_items=[
        {"slack_user_id": "U1234567", "task": "로그인 기능 구현", "due": "5/10"},
        {"slack_user_id": "U7654321", "task": "API 문서 작성", "due": "5/12"},
    ]
)
# → 스레드에 @멘션, 각 담당자에게 DM 전송
```

---

## 6. WorkB 가입 유저에게 DM

> 채널 멤버 중 WorkB 이메일과 일치하는 유저에게만 DM을 전송합니다.
> 채널에 없거나 이메일이 다르면 `ValueError` 발생.

```python
await slack.send_dm_to_workspace_member(
    channel_id="C1234567",
    workb_email="user@company.com",
    text="회의록 검토 요청이 도착했습니다."
)
```

---

## 7. 채널 전원에게 DM (미가입자 포함)

```python
member_ids = await slack.get_channel_members("C1234567")
for uid in member_ids:
    try:
        dm_ch = await slack.open_dm(uid)
        await slack.send_message(channel_id=dm_ch, text="공지사항입니다.")
    except Exception as e:
        logger.warning(f"DM 실패 ({uid}): {e}")
```

---

## 8. 채널 멤버 및 유저 정보 조회

```python
# 채널 멤버 user_id 목록
member_ids = await slack.get_channel_members("C1234567")
# ["U1234567", "U7654321", ...]

# user_id → 이름·이메일
info = await slack.get_user_info("U1234567")
# {"id": "U1234567", "name": "홍길동", "email": "hong@company.com"}
```

---

## 9. workspace_id로 채널 ID 조회

> 어드민이 드롭다운에서 채널을 선택하면 `integrations.extra_config.channel_id`에 저장됩니다.
> `IntegrationResponse.selected_channel_id`로 현재 선택된 채널을 프론트에 반환합니다.

채널 목록 드롭다운용 조회 (`GET /integrations/workspaces/{id}/slack/channels`):

```python
from app.domains.integration.service import get_slack_channel

channels = await get_slack_channel(db, workspace_id)
# [{"id": "C1234567", "name": "general"}, ...]
```

채널 선택 저장 (`PATCH /integrations/slack/channel?workspace_id={id}`):

```python
from app.domains.integration.service import save_slack_channel

await save_slack_channel(db, workspace_id, channel_id="C1234567")
```

service.py에서 저장된 채널 ID 꺼내기:

```python
from app.domains.integration.repository import get_integration
from app.domains.integration.models import ServiceType

integration = get_integration(db, workspace_id, ServiceType.slack)
channel_id = integration.extra_config.get("channel_id")
```

> **⚠️ TODO:** `IntegrationResponse`에 `selected_channel_id` 필드 추가 필요.
> 프론트 드롭다운이 저장된 채널을 pre-select하려면 `schemas.py`와 `router.py` 수정 필요.
> 설계 근거: `docs/guides/api_design.md` 항목 7 참고.

---

## 주의사항

- `channel_id`는 채널명(`#general`)이 아닌 **ID**(`C1234567`)를 사용합니다.
- 봇이 채널에 없어도 `chat:write.public` 스코프로 메시지 전송은 가능합니다.
- `pin_message`는 봇이 채널 멤버여야 합니다. 반드시 `join_channel` 먼저 호출하세요.
- `send_dm_to_workspace_member`는 채널 멤버 전체를 순회하므로 멤버가 많은 채널에서는 느릴 수 있습니다.
- `send_action_items`는 `slack_user_id`(U로 시작하는 ID)를 직접 받습니다. 이메일 → user_id 변환은 service.py에서 미리 처리하세요.
- WorkB 미가입자도 Slack `user_id`를 알면 `open_dm` + `send_message`로 DM 전송 가능합니다.
- Slack API 에러는 `ValueError`로 변환됩니다. `router.py`에서 `HTTPException(400)`으로 처리하세요.
- **필요한 OAuth 스코프**: `chat:write`, `chat:write.public`, `channels:read`, `channels:join`, `users:read`, `users:read.email`, `im:write`, `files:write`, `pins:write`
- 스코프 추가 후에는 반드시 워크스페이스 **재연동** 필요 (기존 토큰에 새 스코프 미포함).

```python
# router.py 패턴
try:
    await slack.send_method(...)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```
