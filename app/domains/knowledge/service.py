# app\domains\knowledge\service.py
"""                                                                                                             내부 문서 수집(ingest) 파이프라인.                                                                                         
                                                                                                                흐름:                                                                                                            파일 업로드 → 텍스트 추출 → 청크 분할 → OpenAI 임베딩 → ChromaDB 저장                                                    
                                                                                                                워크스페이스 격리:
    컬렉션명 = ws_{workspace_id}_docs                                                                                        
    워크스페이스마다 별도 컬렉션 → A팀 문서가 B팀에 노출되지 않음.                                                           
    search_internal_db 툴도 동일한 컬렉션명 규칙을 따름 (agent_utils.py 참조).                                               
""" 
import io
import re
from datetime import datetime
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.domains.knowledge.agent_utils import get_collection 

# -- 청크 분할기 --
# RecursiveCharacterTextSplitter 동작 방식:
#   separators 목록을 순서대로 시도 -> 청크가 chunk_size 이하가 될 때까지 재귀.
#  "\n\n" 실패 → "\n" → "。" → ". " → ...
#
# chunk_size=800: GPT 기준 약 600토큰.
#   너무 크면 노이즈 증가(관련 없는 내용 포함), 너무 작으면 맥락 손실.
#
# chunk_overlap=100:
#   청크 경계에서 문장이 잘릴 때 양쪽 청크에 100자씩 중복 포함.
#   "따라서 다음과 같이 결정한다" 같은 문장이 잘려도 검색 누락 방지.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", ". ", " ", ""], # 한국어 문장 부호 우선
)

def _extract_pdf(file_bytes: bytes) -> str:
    """
    PDF -> 텍스트

    pypdf는 PDF 내부 텍스트 레이어를 파싱.
    스캔 이미지 PDF(텍스트 레이어 없음)는 빈 문자열 반환.
    -> vision 도메인 analyze_image()로 OCR 처리 필요.

    페이지 구분을 "\n\n"으로 합쳐
    청크 분할기가 페이지 경계를 자연 분리점으로 인식하게 함/
    """
    from pypdf import PdfReader
    redear = 