"""Hybrid retrieval: dense vectors (Qdrant) + keyword (BM25), fused with RRF or a weighted sum."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.embeddings import Embedder, EmbeddingError
from app.core.logging import get_logger
from app.core.vectorstore import VectorStore, VectorStoreError
from app.ingestion.models import Chunk
from app.retrieval.bm25 import BM25Index

logger = get_logger(__name__)

Mode = Literal["hybrid", "vector", "bm25"]
FusionMethod = Literal["rrf", "weighted"]


class RetrievalError(RuntimeError):
    """Every retrieval backend failed."""


class RetrievedChunk(BaseModel):
    """A retrieved chunk with its fused score and per-method diagnostics."""

    chunk_id: str
    doc_id: str
    filename: str
    text: str
    score: float
    page: int | None = None
    section: str | None = None
    vector_rank: int | None = None  # 1-based rank in the vector list (None if absent)
    bm25_rank: int | None = None
    vector_score: float | None = None
    bm25_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def sources(self) -> list[str]:
        return [n for n, r in (("vector", self.vector_rank), ("bm25", self.bm25_rank)) if r is not None]


# --------------------------------------------------------------------------- fusion (pure)
def fuse_rrf(rank_lists: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank_in_list(d)), ranks 1-based."""
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for rank, key in enumerate(ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def _min_max(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi - lo < 1e-12:
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def fuse_weighted(
    vector_scores: dict[str, float], bm25_scores: dict[str, float], vector_weight: float = 0.5
) -> dict[str, float]:
    """Weighted sum of min-max normalised scores; a chunk missing from one list contributes 0 there."""
    v, b = _min_max(vector_scores), _min_max(bm25_scores)
    keys = set(v) | set(b)
    return {k: vector_weight * v.get(k, 0.0) + (1.0 - vector_weight) * b.get(k, 0.0) for k in keys}


# --------------------------------------------------------------------------- retriever
class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25: BM25Index,
        *,
        fusion: FusionMethod = "weighted",
        rrf_k: int = 60,
        vector_weight: float = 0.7,
        candidate_multiplier: int = 4,
    ) -> None:
        if fusion not in ("rrf", "weighted"):
            raise ValueError(f"unknown fusion method: {fusion}")
        if not 0.0 <= vector_weight <= 1.0:
            raise ValueError("vector_weight must be within [0, 1]")
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25 = bm25
        self.fusion = fusion
        self.rrf_k = rrf_k
        self.vector_weight = vector_weight
        self.candidate_multiplier = max(1, candidate_multiplier)

    @classmethod
    def from_settings(
        cls, settings: Settings, embedder: Embedder, vector_store: VectorStore, bm25: BM25Index
    ) -> HybridRetriever:
        return cls(
            embedder, vector_store, bm25,
            fusion=settings.fusion_method, rrf_k=settings.rrf_k, vector_weight=settings.vector_weight,
        )

    # ------------------------------------------------------------------ public
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        doc_ids: Sequence[str] | None = None,
        mode: Mode = "hybrid",
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if mode not in ("hybrid", "vector", "bm25"):
            raise ValueError(f"unknown mode: {mode}")
        query = (query or "").strip()
        if not query:
            return []

        n_candidates = max(top_k * self.candidate_multiplier, 20)
        vec_hits: list[tuple[Chunk, float]] = []
        bm25_hits: list[tuple[Chunk, float]] = []
        vec_error: Exception | None = None

        if mode in ("hybrid", "vector"):
            try:
                vec_hits = self.vector_store.search(self.embedder.embed_query(query), n_candidates, doc_ids)
            except (EmbeddingError, VectorStoreError) as exc:
                vec_error = exc
                if mode == "vector":
                    raise RetrievalError(f"Vector search failed: {exc}") from exc
                logger.warning("Vector search failed (%s); falling back to BM25 only", exc)
        if mode in ("hybrid", "bm25"):
            bm25_hits = self.bm25.search(query, n_candidates, doc_ids)

        if mode == "hybrid" and vec_error is not None and not bm25_hits:
            raise RetrievalError(f"Vector search failed and BM25 found nothing: {vec_error}")

        return self._fuse(vec_hits, bm25_hits, top_k, mode)

    # ------------------------------------------------------------------ internals
    def _fuse(
        self,
        vec_hits: list[tuple[Chunk, float]],
        bm25_hits: list[tuple[Chunk, float]],
        top_k: int,
        mode: Mode,
    ) -> list[RetrievedChunk]:
        chunks: dict[str, Chunk] = {}
        vec_rank: dict[str, int] = {}
        bm25_rank: dict[str, int] = {}
        vec_score: dict[str, float] = {}
        bm25_score: dict[str, float] = {}
        for r, (c, s) in enumerate(vec_hits, start=1):
            chunks[c.chunk_id] = c
            vec_rank.setdefault(c.chunk_id, r)
            vec_score.setdefault(c.chunk_id, s)
        for r, (c, s) in enumerate(bm25_hits, start=1):
            chunks[c.chunk_id] = c
            bm25_rank.setdefault(c.chunk_id, r)
            bm25_score.setdefault(c.chunk_id, s)

        if mode == "vector":
            fused = dict(vec_score)
        elif mode == "bm25":
            fused = dict(bm25_score)
        elif self.fusion == "rrf":
            fused = fuse_rrf([list(vec_rank), list(bm25_rank)], self.rrf_k)
        else:
            fused = fuse_weighted(vec_score, bm25_score, self.vector_weight)

        def sort_key(cid: str) -> tuple:
            best_rank = min(vec_rank.get(cid, 10**9), bm25_rank.get(cid, 10**9))
            return (-fused[cid], best_rank, cid)  # deterministic tie-break

        out: list[RetrievedChunk] = []
        for cid in sorted(fused, key=sort_key)[:top_k]:
            c = chunks[cid]
            out.append(
                RetrievedChunk(
                    chunk_id=cid, doc_id=c.doc_id, filename=c.filename, text=c.text, score=float(fused[cid]),
                    page=c.page, section=c.section, metadata=dict(c.metadata),
                    vector_rank=vec_rank.get(cid), bm25_rank=bm25_rank.get(cid),
                    vector_score=vec_score.get(cid), bm25_score=bm25_score.get(cid),
                )
            )
        return out
