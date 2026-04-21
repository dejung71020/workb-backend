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
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)

def _extract_pptx(file_bytes: bytes) -> str:
    """
    PPT/PPTX -> 텍스트.

    슬라이드별 도형(shape) 텍스트 프레임 순회.
    "[슬라이드 N]" 헤더 삽입 -> 검색 결과에서 몇 번째 슬라이드인지 참조 가능.
    차트/이미지 속 텍스트는 추출 불가 -> vision 도메인 OCR 필요.
    """
    from pptx import Presentation
    prs = Presentation(io.BytesIO(file_bytes))
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs).strip()
                    if line:
                        texts.append(line)
        if texts:
            slides.append(f"[슬라이드 (i)]\n" + "\n".join(texts))
    return "\n\n".join(slides)

def _extract_html(file_bytes: bytes) -> str:
    """
    HTML -> 텍스트.

    제거 태그: script/style(코드 노이즈), nav/header/footer(반복 메뉴 텍스트).
    연속 줄바꿈 3개 이상 -> 2개로 압축해 빈 청크 방지.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(file_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(fr"\n{3,}", "\n\n", text).strip()

def ingest_document(
    workspace_id: int,
    filename: str,
    file_bytes: bytes,
    file_type: str,
    title: Optional[str] = None,
) -> dict:
    """
    문서 수집 전체 파이프라인.

    Args:
        workspace_id: 워크스페이스 ID, 컬렉션 격리 키.
        filename: 웝본 파일명. doc_id 및 메타데이터에 사용.
        file_bytes: 업로드된 파일 바이너리.
        file_type: "pdf" | "pptx" | "html".
        title: 문서 제목. None 이면 filename 사용.

    Returns:
        {"doc_id": str, "chunks": int, "title": str}

    중복 업로드 처리:
        doc_id = "{workspace_id}_{filename}" 고정
        청크 ID도 "{doc_id}_{chunk_id}" 고정.
        -> 같은 파일 재업로드 시 upsert가 덮어씀. 벡터 중복 없음
    """
    # 1단계: 텍스트 추출
    if file_type == "pdf":
        raw_text = _extract_pdf(file_bytes)
    elif file_type == "pptx":
        raw_text = _extract_pptx(file_bytes)
    elif file_type == "html":
        raw_text = _extract_html(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {file_type} pdf | pptx | html 만 가능")

    if not raw_text.strip():
        raise ValueError(
            "텍스트를 추출할 수 없습니다. "
            "스캔 이미지 PDF는 vision 도메인 OCR(/api/v1/vision)을 사용하세요."
        )

    # 2단계: 청크 분할
    # 결과: 각 청크 <= 800자, 인접 청크 간 100자 overlap
    chunks = _splitter.split_text(raw_text)

    # 3단계: 메타데이터 구성
    doc_id = f"{workspace_id}_{filename}"
    title = title or filename
    uploaded_at = datetime.now().isoformat()

    ids = [f"{doc_id}_chunk{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "workspace_id": workspace_id,
            "doc_id": doc_id,
            "title": title,
            "filename": filename,
            "file_type": file_type,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "uploaded_at": uploaded_at,
        }
        for i in range(len(chunks))
    ]

    # 4단계: ChromaDB upsert
    # add() 대신 upsert() 이유:
    #   add()는 동일 ID 존재 시 에러 → 재업로드 불가
    #   upsert()는 있으면 덮어쓰고 없으면 삽입 → 재업로드 안전
    collection = get_collection(workspace_id)
    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)

    return {"doc_id": doc_id, "chunks": len(chunks), "title": title}