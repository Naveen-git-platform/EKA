"""Retrieval-quality metrics against the labelled sample questions (evidence-string based)."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.retrieval.hybrid_retriever import HybridRetriever, Mode, RetrievedChunk


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relevant_hits(retrieved: Sequence[RetrievedChunk], question: dict[str, Any]) -> list[bool]:
    """Per retrieved chunk: does it come from a relevant doc AND contain some evidence string?"""
    docs = set(question["relevant_docs"])
    evidence = [_norm(e) for e in question["evidence"]]
    return [r.filename in docs and any(e in _norm(r.text) for e in evidence) for r in retrieved]


def evidence_recall(retrieved: Sequence[RetrievedChunk], question: dict[str, Any]) -> float:
    """Fraction of the question's evidence strings covered by the retrieved set."""
    docs = set(question["relevant_docs"])
    text = " ".join(_norm(r.text) for r in retrieved if r.filename in docs)
    ev = question["evidence"]
    return sum(_norm(e) in text for e in ev) / len(ev)


def reciprocal_rank(retrieved: Sequence[RetrievedChunk], question: dict[str, Any]) -> float:
    for rank, ok in enumerate(relevant_hits(retrieved, question), start=1):
        if ok:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval(
    retriever: HybridRetriever, questions: Iterable[dict[str, Any]], k: int = 5, mode: Mode = "hybrid"
) -> dict[str, float]:
    """Mean evidence-recall@k, MRR@k and hit-rate@k over the questions."""
    recalls, rrs, hits = [], [], []
    for q in questions:
        res = retriever.retrieve(q["question"], top_k=k, mode=mode)
        recalls.append(evidence_recall(res, q))
        rrs.append(reciprocal_rank(res, q))
        hits.append(1.0 if any(relevant_hits(res, q)) else 0.0)
    n = max(len(recalls), 1)
    return {
        f"recall@{k}": sum(recalls) / n,
        f"mrr@{k}": sum(rrs) / n,
        f"hit_rate@{k}": sum(hits) / n,
        "n_questions": float(len(recalls)),
    }
