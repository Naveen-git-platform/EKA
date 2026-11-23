"""Request / response models for the HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ documents
class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    size_bytes: int
    chunk_count: int
    page_count: int | None = None
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    total: int
    total_chunks: int


class UploadItemResult(BaseModel):
    filename: str
    status: Literal["indexed", "replaced", "duplicate", "failed"]
    doc_id: str | None = None
    chunk_count: int | None = None
    page_count: int | None = None
    replaced_doc_id: str | None = None
    error: str | None = None
    error_type: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadItemResult]
    indexed: int = 0
    failed: int = 0


class DeleteResponse(BaseModel):
    deleted: str


# ------------------------------------------------------------------ query
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    doc_ids: list[str] | None = Field(default=None, max_length=50)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    stream: bool = True
    evaluate: bool = False  # run the evaluation pipeline on this answer in the background

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class QueryResponse(BaseModel):
    """Non-streaming result (`stream=false`)."""

    question: str
    answer: str
    ok: bool
    grounded: bool
    citations: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    plan: dict[str, Any]
    critique: dict[str, Any]
    iterations: int
    elapsed_ms: float
    trace: list[dict[str, Any]]
    errors: list[str]
