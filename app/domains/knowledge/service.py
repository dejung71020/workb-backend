# app/domains/knowledge/service.py
"""Internal document ingestion helpers.

This module is kept small because the current router does not expose document
upload endpoints yet. The functions below are safe building blocks for the
future knowledge-base API and keep the merged code importable.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.domains.knowledge.agent_utils import chroma_client


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", ". ", " ", ""],
)


def _collection_name(workspace_id: int) -> str:
    """Return the workspace-scoped Chroma collection name."""
    return f"ws_{workspace_id}_docs"


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page for page in pages if page.strip())


def _extract_text(file_bytes: bytes) -> str:
    """Extract text from a UTF-8 compatible plain text document."""
    return file_bytes.decode("utf-8", errors="ignore")


def extract_document_text(filename: str, file_bytes: bytes) -> str:
    """Extract text from a supported document type."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_bytes)
    return _extract_text(file_bytes)


def ingest_internal_document(
    workspace_id: int,
    filename: str,
    file_bytes: bytes,
    title: str | None = None,
) -> dict[str, Any]:
    """Split a document and store its chunks in a workspace-scoped collection."""
    text = extract_document_text(filename, file_bytes)
    chunks = [chunk for chunk in _splitter.split_text(text) if chunk.strip()]

    if not chunks:
        return {
            "workspace_id": workspace_id,
            "filename": filename,
            "chunk_count": 0,
            "stored": False,
        }

    collection = chroma_client.get_or_create_collection(_collection_name(workspace_id))
    now = datetime.now().isoformat()
    ids = [
        f"workspace-{workspace_id}:{filename}:{index}:{now}"
        for index, _ in enumerate(chunks)
    ]
    metadatas = [
        {
            "workspace_id": workspace_id,
            "filename": filename,
            "title": title or filename,
            "chunk_index": index,
            "created_at": now,
        }
        for index, _ in enumerate(chunks)
    ]

    collection.add(ids=ids, documents=chunks, metadatas=metadatas)

    return {
        "workspace_id": workspace_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "stored": True,
    }
