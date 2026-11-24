from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """A contiguous piece of parsed text with its location (page / section)."""

    text: str
    page: int | None = None
    section: str | None = None


class Chunk(BaseModel):
    """An indexable unit of text. `chunk_id` is stable for (doc_id, chunk_index)."""

    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    filename: str
    page: int | None = None
    section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def index_text(self) -> str:
        """Text used for both embedding and BM25: section context + body.

        Prefixing the section title lets a chunk be found by its heading even when the
        body never repeats it (common in policy documents).
        """
        return f"{self.section}\n{self.text}" if self.section else self.text


class DocumentRecord(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    size_bytes: int
    sha256: str
    chunk_count: int
    page_count: int | None = None
    created_at: str


class IngestionResult(BaseModel):
    doc_id: str
    filename: str
    status: str  # "indexed" | "duplicate" | "replaced"
    chunk_count: int
    page_count: int | None = None
    replaced_doc_id: str | None = None
