from __future__ import annotations

import json

from app.evaluation.models import EvaluationResult
from app.evaluation.run import aggregate_by_category, format_table, main


def res(i, cat, faith, rel=0.5) -> EvaluationResult:
    return EvaluationResult(id=f"e{i}", created_at="2026-01-01T00:00:00+00:00", question=f"q{i}?", answer="a",
                            category=cat, faithfulness=faith, answer_relevancy=rel, overall=faith)


def test_aggregate_by_category_ignores_none():
    out = aggregate_by_category([res(1, "keyword", 1.0), res(2, "keyword", None), res(3, "paraphrase", 0.5), res(4, None, 0.0)])
    assert out["keyword"]["faithfulness"] == 1.0 and out["keyword"]["count"] == 2.0
    assert out["paraphrase"]["faithfulness"] == 0.5 and out["uncategorised"]["faithfulness"] == 0.0
    assert out["keyword"]["context_recall"] is None


def test_format_table_has_rows_and_na_markers():
    from app.evaluation.evaluator import BatchSummary

    results = [res(1, "keyword", 1.0), res(2, "paraphrase", 0.5)]
    summary = BatchSummary(run_id="r", total=2, completed=2, aggregate={"faithfulness": 0.75, "count": 2.0}, results=results)
    table = format_table(summary)
    assert "ALL" in table and "keyword" in table and "paraphrase" in table and "n/a" in table and "0.750" in table


def test_cli_end_to_end_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_DIM", "512")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant"))
    out_file = tmp_path / "results.json"
    code = main(["--ingest-samples", "--limit", "5", "--categories", "standard", "--json", str(out_file)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "ingested employee_handbook.md" in printed and "Evaluating 5 questions" in printed and "ALL" in printed
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(payload["results"]) == 5 and set(payload["by_category"]) == {"standard"}
    assert all(r["source"] == "batch" and r["backend"] == "custom" for r in payload["results"])


def test_cli_without_documents_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_DIM", "512")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant"))
    assert main([]) == 2
    assert "No documents are indexed" in capsys.readouterr().err
