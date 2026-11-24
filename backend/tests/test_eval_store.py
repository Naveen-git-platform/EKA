from __future__ import annotations

import pytest

from app.evaluation.models import EvaluationResult
from app.evaluation.store import EvaluationStore


def mk(i: int, run_id: str | None = None, **kw) -> EvaluationResult:
    base = dict(
        id=f"e{i}", run_id=run_id, created_at=f"2026-01-01T00:00:{i:02d}+00:00", question=f"question {i}?",
        answer=f"answer {i}", contexts=[f"context {i} — ünïcode", "second"], faithfulness=1.0, answer_relevancy=0.5,
        context_precision=0.75, context_recall=None, overall=0.75, unsupported_claims=["bad claim"], errors=[],
        latency_ms=12.5, case_id=f"q{i}", category="standard", ground_truth="gt",
    )
    return EvaluationResult(**(base | kw))


@pytest.fixture
def store(tmp_path):
    return EvaluationStore(tmp_path / "eval.db")


def test_roundtrip_preserves_everything_including_nulls_and_unicode(store):
    r = mk(1, faithfulness=None)
    store.add(r)
    got = store.get("e1")
    assert got == r
    assert got.faithfulness is None and got.context_recall is None
    assert got.contexts[0] == "context 1 — ünïcode"


def test_get_unknown_is_none(store):
    assert store.get("nope") is None


def test_add_same_id_replaces(store):
    store.add(mk(1, answer="old"))
    store.add(mk(1, answer="new"))
    assert store.count() == 1 and store.get("e1").answer == "new"


def test_list_is_newest_first_with_pagination_and_run_filter(store):
    for i in range(1, 6):
        store.add(mk(i, run_id="A" if i % 2 else "B"))
    assert [r.id for r in store.list()] == ["e5", "e4", "e3", "e2", "e1"]
    assert [r.id for r in store.list(limit=2)] == ["e5", "e4"]
    assert [r.id for r in store.list(limit=2, offset=2)] == ["e3", "e2"]
    assert [r.id for r in store.list(run_id="A")] == ["e5", "e3", "e1"]
    assert store.count() == 5 and store.count("B") == 2 and store.count("zzz") == 0


def test_aggregate_ignores_nulls(store):
    store.add(mk(1, faithfulness=1.0, context_recall=None, overall=0.8))
    store.add(mk(2, faithfulness=0.5, context_recall=1.0, overall=0.6))
    store.add(mk(3, faithfulness=None, context_recall=0.0, overall=None))
    agg = store.aggregate()
    assert agg["faithfulness"] == 0.75  # mean of 1.0 and 0.5, NULL skipped
    assert agg["context_recall"] == pytest.approx(0.5)
    assert agg["overall"] == 0.7 and agg["count"] == 3.0
    assert agg["answer_relevancy"] == 0.5


def test_aggregate_empty_and_filtered(store):
    agg = store.aggregate()
    assert agg["count"] == 0.0 and agg["faithfulness"] is None
    store.add(mk(1, run_id="A", faithfulness=1.0))
    store.add(mk(2, run_id="B", faithfulness=0.0))
    assert store.aggregate("A")["faithfulness"] == 1.0 and store.aggregate("B")["faithfulness"] == 0.0
    assert store.aggregate("missing")["count"] == 0.0


def test_runs_lifecycle(store):
    store.create_run("r1", total=3, name="first", backend="custom")
    run = store.get_run("r1")
    assert run.status == "running" and run.total == 3 and run.completed == 0 and run.name == "first"
    store.add(mk(1, run_id="r1", faithfulness=1.0))
    store.add(mk(2, run_id="r1", faithfulness=0.5))
    run = store.get_run("r1")
    assert run.completed == 2 and run.aggregate["faithfulness"] == 0.75 and "count" not in run.aggregate
    store.finish_run("r1", "completed")
    assert store.get_run("r1").status == "completed"
    store.create_run("r2", total=1)
    assert [r.run_id for r in store.list_runs()] == ["r2", "r1"]
    assert store.get_run("nope") is None


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "eval.db"
    EvaluationStore(path).add(mk(1, run_id="r"))
    again = EvaluationStore(path)
    assert again.get("e1") is not None and again.count() == 1


def test_delete_all(store):
    store.create_run("r", 1)
    store.add(mk(1, run_id="r"))
    store.delete_all()
    assert store.count() == 0 and store.list_runs() == []
