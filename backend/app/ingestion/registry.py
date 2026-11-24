"""SQLite document registry and JSONL chunk store (source of truth for rebuilding indexes)."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.ingestion.models import Chunk, DocumentRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    page_count  INTEGER,
    created_at  TEXT NOT NULL
)
"""


class DocumentRegistry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add(self, rec: DocumentRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?)",
                (
                    rec.doc_id, rec.filename, rec.file_type, rec.size_bytes,
                    rec.sha256, rec.chunk_count, rec.page_count, rec.created_at,
                ),
            )

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def find_by_filename(self, filename: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE filename=? ORDER BY created_at DESC LIMIT 1", (filename,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def list(self) -> list[DocumentRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC, filename").fetchall()
        return [DocumentRecord(**dict(r)) for r in rows]

    def delete(self, doc_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
        return cur.rowcount > 0


class ChunkStore:
    """One JSONL file per document under `store_dir/chunks/`."""

    def __init__(self, store_dir: Path) -> None:
        self.dir = Path(store_dir) / "chunks"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, doc_id: str) -> Path:
        return self.dir / f"{doc_id}.jsonl"

    def save(self, doc_id: str, chunks: list[Chunk]) -> None:
        tmp = self._path(doc_id).with_suffix(".tmp")
        tmp.write_text("\n".join(c.model_dump_json() for c in chunks), encoding="utf-8")
        tmp.replace(self._path(doc_id))

    def load(self, doc_id: str) -> list[Chunk]:
        p = self._path(doc_id)
        if not p.exists():
            return []
        return [Chunk.model_validate_json(line) for line in p.read_text(encoding="utf-8").splitlines() if line]

    def delete(self, doc_id: str) -> None:
        self._path(doc_id).unlink(missing_ok=True)

    def iter_chunks(self) -> Iterator[Chunk]:
        for p in sorted(self.dir.glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line:
                    yield Chunk.model_validate_json(line)
