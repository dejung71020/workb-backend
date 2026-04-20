# app\domains\vision\service.py
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from app.domains.vision.agent_utils import (
    analyze_image, convert_pptx_to_images, analyze_ppt_slide_image
)
from app.domains.vision import repository

def analyze_screen_share(image_bytes: bytes, meeting_id: str, seq: int | None) -> dict:
    analysis = analyze_image(image_bytes, meeting_id, seq)
    repository.save_analysis(meeting_id=meeting_id, data=analysis)
    return {"timestamp": datetime.now(), **analysis}

def get_analyses(meeting_id: str) -> list[dict]:
    return repository.get_analyses(meeting_id)

def analyze_ppt(ppt_bytes: bytes, meeting_id: str) -> list[dict]:
    images = convert_pptx_to_images(ppt_bytes)

    def analyze_one(args):
        i, image_bytes = args
        analysis = analyze_ppt_slide_image(image_bytes, i + 1, meeting_id)
        results.append({
            "slide_number": i + 1,
            "text": analysis.get("ocr_text", ""),
            "chart_description": analysis.get("chart_description", ""),
            "key_points": analysis.get("key_points", []),
            "summary": analysis.get("summary", ""),
        })

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(analyze_one, enumerate(images)))

    return results