"""Read-only data for the dashboard: corpus/evaluation statistics and the 3D knowledge map."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import ContainerDep
from app.core.logging import get_logger
from app.core.vectorstore import VectorStoreError
from app.retrieval.projection import project_3d

logger = get_logger(__name__)
router = APIRouter(prefix="/insights", tags=["insights"])


class EvaluationSummary(BaseModel):
    count: int
    runs: int
    aggregate: dict[str, float | None]
    avg_latency_ms: float | None = None


class StatsResponse(BaseModel):
    documents: int
    chunks: int
    file_types: dict[str, int]
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    evaluation: EvaluationSummary
    benchmark: dict[str, Any] | None = None


class MapPoint(BaseModel):
    chunk_id: str
    doc_id: str
    filename: str
    page: int | None = None
    section: str | None = None
    snippet: str
    x: float
    y: float
    z: float


class MapDocument(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class MapResponse(BaseModel):
    points: list[MapPoint]
    documents: list[MapDocument]
    total: int
    truncated: bool
    explained_variance: list[float]


def _load_benchmark(path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@router.get("/stats", response_model=StatsResponse)
def stats(container: ContainerDep) -> StatsResponse:
    settings = container.settings
    docs = container.ingestion.list_documents()
    recent = container.eval_store.list(limit=200)
    latencies = [r.latency_ms for r in recent if r.latency_ms is not None]
    return StatsResponse(
        documents=len(docs),
        chunks=sum(d.chunk_count for d in docs),
        file_types=dict(Counter(d.file_type for d in docs)),
        llm_provider=settings.llm_provider,
        llm_model=settings.resolved_llm_model,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        evaluation=EvaluationSummary(
            count=container.eval_store.count(),
            runs=len(container.eval_store.list_runs(limit=200)),
            aggregate=container.eval_store.aggregate(),
            avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else None,
        ),
        benchmark=_load_benchmark(settings.benchmark_results_path),
    )


@router.get("/map", response_model=MapResponse)
def knowledge_map(
    container: ContainerDep,
    max_points: int = Query(2000, ge=1, le=5000),
    doc_ids: list[str] | None = Query(None),
) -> MapResponse:
    """Every indexed chunk as a point in 3D (PCA of its embedding), so the UI can show what the retriever saw."""
    try:
        rows = container.vector_store.scroll_vectors(doc_ids or None, limit=max_points)
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    coords, explained = project_3d([vec for _, vec in rows])
    points = [
        MapPoint(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            filename=chunk.filename,
            page=chunk.page,
            section=chunk.section,
            snippet=" ".join(chunk.text.split())[:160],
            x=round(float(c[0]), 5),
            y=round(float(c[1]), 5),
            z=round(float(c[2]), 5),
        )
        for (chunk, _), c in zip(rows, coords, strict=True)
    ]
    per_doc = Counter(p.doc_id for p in points)
    names = {p.doc_id: p.filename for p in points}
    documents = [MapDocument(doc_id=d, filename=names[d], chunks=n) for d, n in per_doc.most_common()]
    total = sum(container.vector_store.count(d) for d in doc_ids) if doc_ids else container.vector_store.count()
    return MapResponse(
        points=points, documents=documents, total=total, truncated=len(points) < total,
        explained_variance=[round(v, 4) for v in explained],
    )
