# app\domains\vision\service.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.domains.vision.agent_utils import (
    analyze_image, convert_pptx_to_images, analyze_ppt_slide_image
)
from app.domains.vision import repository
from app.utils.time_utils import now_kst

async def analyze_screen_share(image_bytes: bytes, meeting_id: int, seq: int | None) -> dict:
    analysis = await analyze_image(image_bytes, meeting_id, seq)
    repository.save_analysis(meeting_id=meeting_id, data=analysis)
    return {"timestamp": now_kst(), **analysis}

async def get_analyses(meeting_id: int) -> list[dict]:
    return repository.get_analyses(meeting_id)

async def analyze_ppt(ppt_bytes: bytes, meeting_id: int) -> list[dict]:
    # convert_pptx_to_images는 subprocess + 파일 I/O -> executor에서 실행
    loop = asyncio.get_event_loop()
    images = await loop.run_in_executor(
        None,
        convert_pptx_to_images,
        ppt_bytes
    )

    # 슬라이드 분석은 LLM 호출 -> asyncio.gather로 병렬 처리
    analyses = await asyncio.gather(*[
        analyze_ppt_slide_image(image_bytes, i + 1, meeting_id)
        for i, image_bytes in enumerate(images)
    ])
    
    return [
        {
            "slide_number": i + 1,
            "text": a.get("ocr_text", ""),
            "chart_description": a.get("chart_description", ""),
            "key_points": a.get("key_points", []),
            "summary": a.get("summary", ""),
        }
        for i, a in enumerate(analyses)
    ]