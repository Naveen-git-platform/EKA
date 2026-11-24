"""Retriever agent: runs the planner's queries through the hybrid retriever and merges the results."""
from __future__ import annotations

import asyncio
from typing import Any

from app.agents.base import get_emitter
from app.agents.state import EVENT_RETRIEVAL, AgentState, chunk_summary
from app.core.logging import get_logger
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalError

logger = get_logger(__name__)


def merge_chunks(existing: list[dict[str, Any]], new: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Union by chunk_id keeping the best score per chunk, ordered best-first and capped at `limit`."""
    by_id: dict[str, dict[str, Any]] = {c["chunk_id"]: c for c in existing}
    for c in new:
        cur = by_id.get(c["chunk_id"])
        if cur is None or c["score"] > cur["score"]:
            by_id[c["chunk_id"]] = c
    ranked = sorted(by_id.values(), key=lambda c: (-c["score"], c["chunk_id"]))
    return ranked[:limit]


class RetrieverAgent:
    def __init__(self, retriever: HybridRetriever, default_top_k: int = 5) -> None:
        self.retriever = retriever
        self.default_top_k = default_top_k

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        queries = state.get("queries") or [state.get("standalone_query") or state["query"]]
        top_k = state.get("top_k") or self.default_top_k
        doc_ids = state.get("doc_ids") or None
        iteration = state.get("iteration", 0) + 1

        found: list[dict[str, Any]] = []
        errors: list[str] = []
        succeeded = 0
        for q in queries:  # sequential: the embedded Qdrant client is not designed for concurrent use
            try:
                results = await asyncio.to_thread(self.retriever.retrieve, q, top_k, doc_ids=doc_ids)
                found.extend(r.model_dump() for r in results)
                succeeded += 1
            except (RetrievalError, ValueError) as exc:
                logger.warning("Retrieval failed for %r: %s", q, exc)
                errors.append(f"retriever: {exc}")

        retrieved = merge_chunks(state.get("retrieved", []), found, limit=max(top_k * 2, top_k))
        used = list(dict.fromkeys([*state.get("used_queries", []), *queries]))
        get_emitter()(
            {
                "type": EVENT_RETRIEVAL,
                "iteration": iteration,
                "queries": queries,
                "chunks": [chunk_summary(c) for c in retrieved],
                "total": len(retrieved),
            }
        )
        return {
            "retrieved": retrieved,
            "iteration": iteration,
            "used_queries": used,
            "retrieval_failed": succeeded == 0,
            "errors": errors,
        }
