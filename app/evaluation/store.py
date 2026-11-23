"""SQLite persistence for evaluation results and batch runs."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.models import METRIC_NAMES, EvaluationResult, RunInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    backend TEXT NOT NULL,
    question TEXT NOT NULL,
    ground_truth TEXT,
    answer TEXT NOT NULL,
    contexts_json TEXT NOT NULL,
    faithfulness REAL,
    answer_relevancy REAL,
    context_precision REAL,
    context_recall REAL,
    overall REAL,
    unsupported_json TEXT NOT NULL,
    errors_json TEXT NOT NULL,
    latency_ms REAL,
    case_id TEXT,
    category TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_run ON evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_created ON evaluations(created_at);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    backend TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class EvaluationStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ results
    def add(self, r: EvaluationResult) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO evaluations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.id, r.run_id, r.created_at, r.source, r.backend, r.question, r.ground_truth, r.answer,
                 json.dumps(r.contexts, ensure_ascii=False), r.faithfulness, r.answer_relevancy, r.context_precision,
                 r.context_recall, r.overall, json.dumps(r.unsupported_claims, ensure_ascii=False),
                 json.dumps(r.errors, ensure_ascii=False), r.latency_ms, r.case_id, r.category),
            )

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> EvaluationResult:
        d = dict(row)
        d["contexts"] = json.loads(d.pop("contexts_json"))
        d["unsupported_claims"] = json.loads(d.pop("unsupported_json"))
        d["errors"] = json.loads(d.pop("errors_json"))
        return EvaluationResult(**d)

    def get(self, eval_id: str) -> EvaluationResult | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM evaluations WHERE id=?", (eval_id,)).fetchone()
        return self._row_to_result(row) if row else None

    def list(self, *, limit: int = 50, offset: int = 0, run_id: str | None = None) -> list[EvaluationResult]:
        sql, args = "SELECT * FROM evaluations", []
        if run_id:
            sql += " WHERE run_id=?"
            args.append(run_id)
        sql += " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_to_result(r) for r in rows]

    def count(self, run_id: str | None = None) -> int:
        with self._connect() as conn:
            if run_id:
                return conn.execute("SELECT COUNT(*) FROM evaluations WHERE run_id=?", (run_id,)).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]

    def aggregate(self, run_id: str | None = None) -> dict[str, float | None]:
        """Mean of each metric over rows where it is not NULL, plus `overall` and `count`."""
        cols = [*METRIC_NAMES, "overall"]
        sel = ", ".join(f"AVG({c})" for c in cols)
        sql = f"SELECT {sel}, COUNT(*) FROM evaluations" + (" WHERE run_id=?" if run_id else "")
        with self._connect() as conn:
            row = conn.execute(sql, (run_id,) if run_id else ()).fetchone()
        out: dict[str, float | None] = {
            c: (round(row[i], 4) if row[i] is not None else None) for i, c in enumerate(cols)
        }
        out["count"] = float(row[len(cols)])
        return out

    def delete_all(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM evaluations")
            conn.execute("DELETE FROM runs")

    # ------------------------------------------------------------------ runs
    def create_run(self, run_id: str, total: int, *, name: str | None = None, backend: str = "custom") -> None:
        with self._lock, self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
                         (run_id, now_iso(), name, "running", total, backend))

    def finish_run(self, run_id: str, status: str = "completed") -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))

    def get_run(self, run_id: str) -> RunInfo | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_info(dict(row)) if row else None

    def list_runs(self, limit: int = 20) -> list[RunInfo]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._run_info(dict(r)) for r in rows]

    def _run_info(self, row: dict) -> RunInfo:
        agg = self.aggregate(row["run_id"])
        return RunInfo(
            run_id=row["run_id"], created_at=row["created_at"], name=row["name"], status=row["status"],
            total=row["total"], completed=int(agg.pop("count") or 0), backend=row["backend"], aggregate=agg,
        )
