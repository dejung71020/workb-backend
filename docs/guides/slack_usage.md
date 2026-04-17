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

## 2. 채널에 회의록 전송

```python
await slack.send_minutes(
    channel_id="C1234567",
    meeting_title="4월 스프린트 회의",
    minutes_text="오늘 회의에서는 A, B, C를 논의했습니다.",
    action_items=["API 문서 작성", "리뷰 요청"],        # 선택
    link_url="https://workb.app/meetings/1/minutes"    # 선택
)
```

---

## 3. WorkB 가입 유저에게 DM

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

## 4. 채널 전원에게 DM (미가입자 포함)

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

## 5. workspace_id로 채널 ID 조회

> 어드민이 드롭다운에서 채널을 선택하면 `integrations.extra_config.channel_id`에 저장됩니다.
> 이후 서비스 코드에서는 `channel_id`를 직접 받지 않아도 됩니다.

```python
from app.domains.integration.service import get_slack_channel_id

channel_id = get_slack_channel_id(db, workspace_id)
await slack.send_minutes(channel_id=channel_id, ...)
```

채널 목록 드롭다운용 조회:

```python
channels = await slack.get_public_channels()
# [{"id": "C1234567", "name": "general"}, ...]
```

채널 선택 저장 (프론트 → `PATCH /integrations/slack/channel?workspace_id={id}`):

```python
from app.domains.integration.service import save_slack_channel

save_slack_channel(db, workspace_id, channel_id="C1234567")
```

---

## 6. 채널 멤버 및 유저 정보 조회

```python
# 채널 멤버 user_id 목록
member_ids = await slack.get_channel_members("C1234567")
# ["U1234567", "U7654321", ...]

# user_id → 이름·이메일
info = await slack.get_user_info("U1234567")
# {"id": "U1234567", "name": "홍길동", "email": "hong@company.com"}
```

---

## 주의사항

- `channel_id`는 채널명(`#general`)이 아닌 **ID**(`C1234567`)를 사용합니다.
- 봇이 채널에 없어도 `chat:write.public` 스코프로 전송 가능합니다.
- `send_dm_to_workspace_member`는 채널 멤버 전체를 순회하므로 멤버가 많은 채널에서는 느릴 수 있습니다.
- WorkB 미가입자도 Slack `user_id`를 알면 `open_dm` + `send_message`로 DM 전송 가능합니다.
- Slack API 에러는 `ValueError`로 변환됩니다. `router.py`에서 `HTTPException(400)`으로 처리하세요.

```python
# router.py 패턴
try:
    await slack.send_message(...)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```