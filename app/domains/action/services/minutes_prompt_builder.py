def build_minutes_from_transcript_prompt(utterances: list[dict]) -> str:
    """
    요약 데이터가 없을 때 원본 발화 목록으로 회의록 프롬프트를 생성합니다.
    """
    transcript = _format_transcript(utterances)

    return f"""당신은 전문 회의록 작성 AI입니다.

[임무]
아래 회의 발화 내용을 분석하여 회의록을 작성하세요.
제목, 일시, 참석자, 주요 논의 사항, 결정 사항, 액션 아이템, 미결 사항을 반드시 포함하세요.

[작성 원칙]
1. 발화 내용에 근거한 사실만 기재하고, 언급되지 않은 내용을 임의로 생성하지 마십시오.
2. 정보가 불분명한 필드는 "(확인 필요)"로 표시하십시오.
3. 마크다운 형식으로 출력하고 회의록 본문만 출력하십시오.

[회의 발화 — 이 내용만 회의록에 반영하십시오]
{transcript}
"""


def _format_transcript(utterances: list[dict], max_chars: int = 6000) -> str:
    """발화 목록을 '화자: 내용' 형식의 텍스트로 변환합니다."""
    lines: list[str] = []
    total = 0
    for u in utterances:
        speaker = u.get("speaker_label") or u.get("speaker_id") or "Unknown"
        content = (u.get("content") or "").strip()
        if not content:
            continue
        line = f"{speaker}: {content}"
        total += len(line)
        if total > max_chars:
            lines.append("(...이하 발화 생략)")
            break
        lines.append(line)
    return "\n".join(lines) if lines else "(발화 데이터 없음)"
