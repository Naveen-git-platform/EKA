"""Thin Qdrant wrapper. Works with embedded local storage, in-memory, or a Qdrant server."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from app.core.config import Settings
from app.core.logging import get_logger
from app.ingestion.models import Chunk

logger = get_logger(__name__)

_NAMESPACE = uuid.UUID("6f1d3a52-9c1e-4c53-9d0b-5a8e1b7c2f10")


class VectorStoreError(RuntimeError):
    """Vector database operation failed or is misconfigured."""


def point_id(chunk_id: str) -> str:
    """Deterministic UUID so re-upserting a chunk overwrites instead of duplicating."""
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


def make_client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, timeout=30)
    settings.qdrant_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(settings.qdrant_path))


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int) -> None:
        self.client = client
        self.collection = collection
        self.dim = dim
        self.ensure_collection()

    @classmethod
    def in_memory(cls, collection: str = "test", dim: int = 64) -> VectorStore:
        return cls(QdrantClient(":memory:"), collection, dim)

    @classmethod
    def from_settings(cls, settings: Settings, dim: int | None = None) -> VectorStore:
        return cls(make_client(settings), settings.qdrant_collection, dim or settings.embedding_dim)

    def ensure_collection(self) -> None:
        try:
            if self.client.collection_exists(self.collection):
                info = self.client.get_collection(self.collection)
                vectors = info.config.params.vectors
                existing = vectors.size if hasattr(vectors, "size") else None
                if existing is not None and existing != self.dim:
                    raise VectorStoreError(
                        f"Collection '{self.collection}' has dim {existing} but embedder produces {self.dim}. "
                        "Use a different QDRANT_COLLECTION or re-index after changing the embedding model."
                    )
                return
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d)", self.collection, self.dim)
        except VectorStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Could not initialise Qdrant collection: {exc}") from exc

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunks and vectors must have the same length")
        if not chunks:
            return
        points = [
            models.PointStruct(id=point_id(c.chunk_id), vector=list(v), payload=c.model_dump())
            for c, v in zip(chunks, vectors, strict=True)
        ]
        try:
            for i in range(0, len(points), 128):
                self.client.upsert(self.collection, points=points[i : i + 128], wait=True)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

    @staticmethod
    def _doc_filter(doc_ids: Sequence[str] | None) -> models.Filter | None:
        if not doc_ids:
            return None
        return models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=list(doc_ids)))])

    def search(
        self, vector: Sequence[float], top_k: int, doc_ids: Sequence[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        try:
            res = self.client.query_points(
                self.collection,
                query=list(vector),
                limit=top_k,
                query_filter=self._doc_filter(doc_ids),
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc
        return [(Chunk(**p.payload), float(p.score)) for p in res.points if p.payload]

    def delete_document(self, doc_id: str) -> None:
        try:
            self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(filter=self._doc_filter([doc_id])),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Qdrant delete failed: {exc}") from exc

    def count(self, doc_id: str | None = None) -> int:
        flt = self._doc_filter([doc_id]) if doc_id else None
        return int(self.client.count(self.collection, count_filter=flt, exact=True).count)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass
