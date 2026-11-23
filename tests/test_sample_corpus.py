"""Guards the bundled sample corpus and eval ground truth used by later phases."""
from __future__ import annotations

import json
import re

import pytest

from tests.conftest import EVAL_QUESTIONS, SAMPLE_DOCS

EXPECTED_DOCS = {"employee_handbook.md", "security_policy.docx", "product_faq.txt", "incident_runbook.pdf"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


@pytest.fixture
def loaded(ingestion):
    for f in sorted(SAMPLE_DOCS.iterdir()):
        ingestion.ingest_path(f)
    return ingestion


def test_all_sample_docs_present():
    assert {p.name for p in SAMPLE_DOCS.iterdir()} == EXPECTED_DOCS


def test_sample_docs_ingest_with_expected_metadata(loaded):
    docs = {d.filename: d for d in loaded.list_documents()}
    assert set(docs) == EXPECTED_DOCS
    assert all(d.chunk_count >= 2 for d in docs.values())
    chunks = list(loaded.chunk_store.iter_chunks())
    pdf_pages = {c.page for c in chunks if c.filename == "incident_runbook.pdf"}
    assert pdf_pages == {1, 2}
    assert any(c.section and "Passwords" in c.section for c in chunks if c.filename == "security_policy.docx")
    assert any(c.section and "Paid Time Off" in c.section for c in chunks if c.filename == "employee_handbook.md")


def test_eval_questions_schema():
    qs = json.loads(EVAL_QUESTIONS.read_text(encoding="utf-8"))
    assert len(qs) >= 30
    assert len({q["id"] for q in qs}) == len(qs)
    assert {q["category"] for q in qs} == {"standard", "paraphrase", "keyword"}
    for q in qs:
        assert q["question"].endswith("?")
        assert q["ground_truth"] and q["evidence"]
        assert set(q["relevant_docs"]) <= EXPECTED_DOCS


def test_every_evidence_string_lands_in_a_relevant_chunk(loaded):
    """If this fails, chunking split an answer across chunks or the ground truth is wrong."""
    chunks = list(loaded.chunk_store.iter_chunks())
    for q in json.loads(EVAL_QUESTIONS.read_text(encoding="utf-8")):
        for ev in q["evidence"]:
            found = [c for c in chunks if c.filename in q["relevant_docs"] and _norm(ev) in _norm(c.text)]
            assert found, f"{q['id']}: evidence {ev!r} not found intact in any relevant chunk"
