"""Shared state, event types and helpers for the multi-agent graph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

# ---- streaming event types (the API serialises these as Server-Sent Events) -------------------------------
EVENT_PLAN = "plan"
EVENT_RETRIEVAL = "retrieval"
EVENT_CRITIQUE = "critique"
EVENT_TOKEN = "token"
EVENT_CITATIONS = "citations"
EVENT_ERROR = "error"
EVENT_DONE = "done"
EVENT_TYPES = (EVENT_PLAN, EVENT_RETRIEVAL, EVENT_CRITIQUE, EVENT_TOKEN, EVENT_CITATIONS, EVENT_ERROR, EVENT_DONE)

NO_ANSWER_TEXT = "I couldn't find enough information in the uploaded documents to answer that question."


class AgentState(TypedDict, total=False):
    # inputs
    query: str
    history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]
    doc_ids: list[str] | None
    top_k: int
    # planner
    plan: dict[str, Any]
    standalone_query: str
    queries: list[str]  # queries the retriever should run next
    used_queries: list[str]  # every query already issued (prevents pointless identical retries)
    # retriever
    retrieved: list[dict[str, Any]]  # accumulated RetrievedChunk dicts (deduplicated)
    retrieval_failed: bool
    iteration: int  # number of retrieval passes performed
    # critic
    critique: dict[str, Any]
    retry: bool
    # answer
    answer: str
    citations: list[dict[str, Any]]
    ok: bool
    # bookkeeping (appended to by every node)
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]


def chunk_summary(chunk: dict[str, Any], snippet_chars: int = 240) -> dict[str, Any]:
    """Compact, UI-friendly view of a retrieved chunk (full text is kept in the citation objects)."""
    text = chunk.get("text", "")
    return {
        "chunk_id": chunk["chunk_id"],
        "filename": chunk.get("filename"),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "score": round(float(chunk.get("score", 0.0)), 5),
        "sources": [n for n, r in (("vector", chunk.get("vector_rank")), ("bm25", chunk.get("bm25_rank"))) if r],
        "snippet": text if len(text) <= snippet_chars else text[: snippet_chars - 1].rstrip() + "…",
    }
