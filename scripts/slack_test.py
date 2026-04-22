# scripts/slack_test.py
import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))
))

from app.infra.clients.slack import SlackClient
from app.infra.clients.session_manager import ClientSessionManager
from app.infra.database.session import SessionLocal
from app.domains.integration.repository import get_integration
from app.domains.integration.models import ServiceType

WORKSPACE_ID = 1

async def main():
    db = SessionLocal()
    try:
        integration = get_integration(db, WORKSPACE_ID, ServiceType.slack)
        if not integration or not integration.access_token:
            print("❌ Slack 연동이 되어있지 않습니다. 먼저 OAuth 연결하세요.")
            return

        client = SlackClient(bot_token=integration.access_token)
        print(f"✅ 토큰 로드 완료\n")

        # [TEST-01] 채널 목록 조회 → 첫 번째 채널 자동 선택
        print("TEST-01: get_public_channels")
        channels = await client.get_public_channels()
        print(f"  채널 {len(channels)}개:")
        for c in channels:
            print(f"    {c['name']} → {c['id']}")
        channel_id = channels[0]['id']
        print(f"  → 테스트 채널: {channels[0]['name']} ({channel_id})\n")

        # [TEST-02] 단순 메시지 전송
        print("TEST-02: send_message")
        result = await client.send_message(
            channel_id=channel_id,
            text="🤖 WorkB 슬랙 테스트 메시지입니다."
        )
        msg_ts = result['ts']
        print(f"  전송 완료 ts={msg_ts}\n")

        # [TEST-03] 스레드 답글
        print("TEST-03: send_message (스레드)")
        await client.send_message(
            channel_id=channel_id,
            text="스레드 답글 테스트입니다.",
            thread_ts=msg_ts
        )
        print("  스레드 답글 완료\n")

        # [TEST-04] 채널 멤버 조회
        print("TEST-04: get_channel_members")
        members = await client.get_channel_members(channel_id=channel_id)
        print(f"  멤버 {len(members)}명: {members}\n")

        # [TEST-05] 유저 정보 조회 → 첫 번째 멤버
        print("TEST-05: get_user_info")
        info = await client.get_user_info(user_id=members[0])
        print(f"  이름={info['name']}, 이메일={info['email']}\n")
        test_user_id = members[0]

        # [TEST-06] Block Kit 회의록 전송
        print("TEST-06: send_minutes")
        ts = await client.send_minutes(
            channel_id=channel_id,
            meeting_title="4월 3주차 팀 회의",
            minutes_text="1. 스프린트 진행 상황 공유\n2. 이슈 리뷰\n3. 다음 주 목표 설정",
            action_items=["API 연동 완료 (대중)", "디자인 수정 (예린)", "테스트 작성 (정우)"],
            link_url="http://localhost:5173/meetings/1/minutes"
        )
        print(f"  회의록 전송 완료 ts={ts}\n")

        # [TEST-07] 채널 참여 + 핀 고정
        print("TEST-07: join_channel + pin_message")
        await client.join_channel(channel_id=channel_id)
        await client.pin_message(channel_id=channel_id, message_ts=ts)
        print("  핀 고정 완료\n")

        # [TEST-08] 액션 아이템 스레드 멘션 + DM
        print("TEST-08: send_action_items")
        await client.send_action_items(
            channel_id=channel_id,
            thread_ts=ts,
            action_items=[
                {"slack_user_id": test_user_id, "task": "슬랙 테스트 완료 확인", "due": "2026-04-25"}
            ]
        )
        print("  액션아이템 멘션 + DM 완료\n")

        # [TEST-09] DM 채널 생성 + 메시지 전송
        print("TEST-09: open_dm + send_message")
        dm_channel = await client.open_dm(user_id=test_user_id)
        await client.send_message(channel_id=dm_channel, text="WorkB DM 테스트입니다.")
        print(f"  DM 전송 완료 dm_channel={dm_channel}\n")

        # [TEST-10] 예약 메시지 전송 (60초 후)
        print("TEST-10: schedule_message")
        import time
        scheduled_id = await client.schedule_message(
            channel_id=channel_id,
            text="⏰ 예약 메시지 테스트입니다. (60초 후 전송)",
            post_at=int(time.time()) + 60
        )
        print(f"  예약 완료 scheduled_id={scheduled_id}\n")

        print("✅ 전체 테스트 완료!")

    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        raise

    finally:
        db.close()
        await ClientSessionManager.close_client()

if __name__ == "__main__":
    asyncio.run(main())