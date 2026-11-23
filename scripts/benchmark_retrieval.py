"""Benchmark vector-only vs BM25-only vs hybrid retrieval on the labelled sample questions.

    python scripts/benchmark_retrieval.py                 # real sentence-transformers model
    python scripts/benchmark_retrieval.py --fake          # hashed lexical embedder (offline, instant)
    python scripts/benchmark_retrieval.py --k 3 --out docs/benchmark_results.json

Metrics (per question category, then overall): evidence recall@k, MRR@k, hit-rate@k. A retrieved chunk counts as a
hit when it comes from a relevant document AND contains the labelled evidence string.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.embeddings import FakeEmbedder, SentenceTransformerEmbedder  # noqa: E402
from app.core.vectorstore import VectorStore  # noqa: E402
from app.ingestion.indexer import IngestionService  # noqa: E402
from app.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402
from app.retrieval.metrics import evaluate_retrieval, load_questions  # noqa: E402

CONFIGS = [
    ("vector only", {"mode": "vector"}),
    ("BM25 only", {"mode": "bm25"}),
    ("hybrid (RRF)", {"mode": "hybrid", "fusion": "rrf"}),
    ("hybrid (weighted 0.5)", {"mode": "hybrid", "fusion": "weighted", "vector_weight": 0.5}),
    ("hybrid (weighted 0.7) [default]", {"mode": "hybrid", "fusion": "weighted", "vector_weight": 0.7}),
]


def run(fake: bool, k: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(_env_file=None, data_dir=Path(tmp) / "data", llm_provider="fake")
        embedder = FakeEmbedder(dim=2048) if fake else SentenceTransformerEmbedder(settings.embedding_model)
        store = VectorStore.in_memory(dim=embedder.dim)
        svc = IngestionService.from_settings(settings, embedder, store)
        for f in sorted((ROOT / "data" / "sample_docs").glob("*")):
            svc.ingest_path(f)
        questions = load_questions(ROOT / "data" / "eval" / "questions.json")
        categories = ["all", *sorted({q["category"] for q in questions})]
        results: dict[str, dict[str, dict[str, float]]] = {}
        for label, cfg in CONFIGS:
            retriever = HybridRetriever(
                embedder, store, svc.bm25, fusion=cfg.get("fusion", "rrf"), vector_weight=cfg.get("vector_weight", 0.5)
            )
            results[label] = {}
            for cat in categories:
                qs = questions if cat == "all" else [q for q in questions if q["category"] == cat]
                results[label][cat] = evaluate_retrieval(retriever, qs, k=k, mode=cfg["mode"])
        store.close()
        return {
            "embedder": "fake-hashed-bow" if fake else settings.embedding_model,
            "k": k,
            "n_documents": len(list((ROOT / "data" / "sample_docs").glob("*"))),
            "n_chunks": len(svc.bm25),
            "n_questions": len(questions),
            "results": results,
        }


def to_markdown(report: dict) -> str:
    k = report["k"]
    cats = list(next(iter(report["results"].values())))
    lines = [
        f"Embedder: `{report['embedder']}` | {report['n_chunks']} chunks | {report['n_questions']} questions | k={k}",
        "",
        "| Retrieval | " + " | ".join(f"{c} (R@{k} / MRR)" for c in cats) + " |",
        "|---|" + "---|" * len(cats),
    ]
    for label, per_cat in report["results"].items():
        cells = [f"{per_cat[c][f'recall@{k}']:.2f} / {per_cat[c][f'mrr@{k}']:.2f}" for c in cats]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="use the offline hashed embedder instead of MiniLM")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", default=None, help="write JSON report here")
    args = ap.parse_args()
    report = run(args.fake, args.k)
    print(to_markdown(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
