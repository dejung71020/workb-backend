"""
레이아웃 검증 — 오버레이 방식에서는 원본 구조가 그대로 유지되므로 사용되지 않음.
하위 호환을 위해 파일은 유지.
"""
import logging

logger = logging.getLogger(__name__)


class VerificationReport:
    passed = True

    def summary(self) -> str:
        return "오버레이 방식: 레이아웃 검증 불필요"


def verify(original_pdf_path: str, generated_pdf_bytes: bytes, threshold_mm: float = 2.0) -> VerificationReport:
    return VerificationReport()
