"""IngestionService: parse -> chunk -> embed -> index (Qdrant + BM25) -> register."""
from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.core.embeddings import Embedder, EmbeddingError
from app.core.logging import get_logger
from app.core.vectorstore import VectorStore, VectorStoreError
from app.ingestion.chunker import chunk_segments
from app.ingestion.errors import (
    DocumentNotFoundError,
    EmptyDocumentError,
    FileTooLargeError,
    IngestionError,
    UnsupportedFileTypeError,
)
from app.ingestion.loaders import SUPPORTED_EXTENSIONS, file_extension, load_document
from app.ingestion.models import Chunk, DocumentRecord, IngestionResult
from app.ingestion.registry import ChunkStore, DocumentRegistry
from app.retrieval.bm25 import BM25Index

logger = get_logger(__name__)

ProgressCallback = Callable[[str, dict], None]
_EMBED_BATCH = 64


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        vector_store: VectorStore,
        registry: DocumentRegistry,
        chunk_store: ChunkStore,
        bm25: BM25Index,
    ) -> None:
        self.settings = settings
        self.embedder = embedder
        self.vector_store = vector_store
        self.registry = registry
        self.chunk_store = chunk_store
        self.bm25 = bm25
        self._lock = threading.RLock()  # one writer at a time keeps registry/vectors/BM25 consistent
        self.refresh_bm25()

    # ----------------------------------------------------------------- construction
    @classmethod
    def from_settings(
        cls, settings: Settings, embedder: Embedder, vector_store: VectorStore | None = None
    ) -> IngestionService:
        return cls(
            settings=settings,
            embedder=embedder,
            vector_store=vector_store or VectorStore.from_settings(settings, dim=embedder.dim),
            registry=DocumentRegistry(settings.data_dir / "registry.db"),
            chunk_store=ChunkStore(settings.store_dir),
            bm25=BM25Index(),
        )

    # ----------------------------------------------------------------- public API
    def refresh_bm25(self) -> None:
        self.bm25.rebuild(self.chunk_store.iter_chunks())

    def list_documents(self) -> list[DocumentRecord]:
        return self.registry.list()

    def get_document(self, doc_id: str) -> DocumentRecord:
        rec = self.registry.get(doc_id)
        if rec is None:
            raise DocumentNotFoundError(f"Document '{doc_id}' not found")
        return rec

    def ingest_path(self, path: str | Path, on_progress: ProgressCallback | None = None) -> IngestionResult:
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise IngestionError(f"Cannot read '{p}': {exc}") from exc
        return self.ingest_bytes(p.name, data, on_progress)

    def ingest_bytes(
        self, filename: str, data: bytes, on_progress: ProgressCallback | None = None
    ) -> IngestionResult:
        progress = on_progress or (lambda stage, info: None)
        filename = Path(filename).name  # never trust client-supplied paths
        t0 = time.perf_counter()

        ext = file_extension(filename)
        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{ext or filename}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        if not data:
            raise EmptyDocumentError(f"'{filename}' is empty")
        if len(data) > self.settings.max_upload_bytes:
            raise FileTooLargeError(
                f"'{filename}' is {len(data) / 1_048_576:.1f} MB; limit is {self.settings.max_upload_mb} MB"
            )

        sha = hashlib.sha256(data).hexdigest()
        doc_id = sha[:16]

        with self._lock:
            existing = self.registry.get(doc_id)
            if existing is not None:
                logger.info("Skipping %s: identical content already indexed as %s", filename, doc_id)
                progress("duplicate", {"doc_id": doc_id})
                return IngestionResult(
                    doc_id=doc_id, filename=existing.filename, status="duplicate",
                    chunk_count=existing.chunk_count, page_count=existing.page_count,
                )

            progress("parsing", {"filename": filename})
            segments = load_document(filename, data)
            pages = {s.page for s in segments if s.page is not None}
            page_count = max(pages) if pages else None

            progress("chunking", {"segments": len(segments)})
            chunks = chunk_segments(
                segments,
                doc_id=doc_id,
                filename=filename,
                chunk_size=self.settings.chunk_size,
                overlap=self.settings.chunk_overlap,
                extra_metadata={"file_type": ext.lstrip(".")},
            )
            if not chunks:
                raise EmptyDocumentError(f"No indexable text found in '{filename}'")

            vectors = self._embed(chunks, progress)

            # Same filename, new content -> replace the old version.
            replaced = self.registry.find_by_filename(filename)
            replaced_id = replaced.doc_id if replaced else None

            progress("indexing", {"chunks": len(chunks)})
            try:
                self.vector_store.upsert(chunks, vectors)
                self.chunk_store.save(doc_id, chunks)
                self.registry.add(
                    DocumentRecord(
                        doc_id=doc_id, filename=filename, file_type=ext.lstrip("."), size_bytes=len(data),
                        sha256=sha, chunk_count=len(chunks), page_count=page_count,
                        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    )
                )
            except Exception as exc:
                self._rollback(doc_id)
                if isinstance(exc, IngestionError | VectorStoreError):
                    raise
                raise IngestionError(f"Failed to index '{filename}': {exc}") from exc

            if replaced_id:
                self._remove(replaced_id)
            self.refresh_bm25()

        logger.info(
            "Ingested %s (doc_id=%s): %d segments -> %d chunks in %.2fs%s",
            filename, doc_id, len(segments), len(chunks), time.perf_counter() - t0,
            f" (replaced {replaced_id})" if replaced_id else "",
        )
        progress("done", {"doc_id": doc_id, "chunks": len(chunks)})
        return IngestionResult(
            doc_id=doc_id, filename=filename, status="replaced" if replaced_id else "indexed",
            chunk_count=len(chunks), page_count=page_count, replaced_doc_id=replaced_id,
        )

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            if self.registry.get(doc_id) is None:
                raise DocumentNotFoundError(f"Document '{doc_id}' not found")
            self._remove(doc_id)
            self.refresh_bm25()
        logger.info("Deleted document %s", doc_id)

    # ----------------------------------------------------------------- internals
    def _embed(self, chunks: list[Chunk], progress: ProgressCallback) -> list[list[float]]:
        vectors: list[list[float]] = []
        texts = [c.index_text for c in chunks]
        try:
            for i in range(0, len(texts), _EMBED_BATCH):
                vectors.extend(self.embedder.embed_documents(texts[i : i + _EMBED_BATCH]))
                progress("embedding", {"done": min(i + _EMBED_BATCH, len(texts)), "total": len(texts)})
        except EmbeddingError as exc:
            raise IngestionError(f"Embedding failed: {exc}") from exc
        if len(vectors) != len(chunks):
            raise IngestionError("Embedder returned a different number of vectors than chunks")
        return vectors

    def _remove(self, doc_id: str) -> None:
        self.vector_store.delete_document(doc_id)
        self.chunk_store.delete(doc_id)
        self.registry.delete(doc_id)

    def _rollback(self, doc_id: str) -> None:
        for step in (
            lambda: self.vector_store.delete_document(doc_id),
            lambda: self.chunk_store.delete(doc_id),
            lambda: self.registry.delete(doc_id),
        ):
            try:
                step()
            except Exception:  # noqa: BLE001, S110 - best-effort cleanup
                logger.exception("Rollback step failed for %s", doc_id)
