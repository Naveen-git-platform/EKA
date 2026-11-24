"""CLI: batch-evaluate the sample question set against the indexed documents.

    python -m app.evaluation.run --ingest-samples --limit 10
    python -m app.evaluation.run --categories paraphrase,keyword --json results.json

Uses whatever LLM / embedding provider is configured in `.env` (LLM_PROVIDER=fake runs a keyless heuristic demo
whose scores are NOT a quality measure).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.logging import setup_logging
from app.evaluation.evaluator import BatchSummary, load_cases
from app.evaluation.models import METRIC_NAMES, EvaluationResult


def aggregate_by_category(results: list[EvaluationResult]) -> dict[str, dict[str, float | None]]:
    groups: dict[str, list[EvaluationResult]] = defaultdict(list)
    for r in results:
        groups[r.category or "uncategorised"].append(r)
    out: dict[str, dict[str, float | None]] = {}
    for cat, rows in sorted(groups.items()):
        agg: dict[str, float | None] = {}
        for m in (*METRIC_NAMES, "overall"):
            vals = [getattr(r, m) for r in rows if getattr(r, m) is not None]
            agg[m] = round(sum(vals) / len(vals), 4) if vals else None
        agg["count"] = float(len(rows))
        out[cat] = agg
    return out


def format_table(summary: BatchSummary) -> str:
    cols = (*METRIC_NAMES, "overall")

    def row(label: str, agg: dict[str, float | None]) -> str:
        cells = ["  n/a " if agg.get(c) is None else f"{agg[c]:6.3f}" for c in cols]
        return f"{label:<14}{int(agg.get('count') or 0):>4}  " + "  ".join(cells)

    header = f"{'':<14}{'n':>4}  " + "  ".join(f"{c[:6]:>6}" for c in cols)
    lines = [header, "-" * len(header), row("ALL", summary.aggregate)]
    for cat, agg in aggregate_by_category(summary.results).items():
        lines.append(row(cat, agg))
    return "\n".join(lines)


async def run(settings: Settings, args: argparse.Namespace) -> int:
    container = Container.build(settings)
    try:
        if args.ingest_samples:
            for p in sorted(Path(settings.sample_docs_dir).glob("*")):
                if p.is_file():
                    res = container.ingestion.ingest_path(p)
                    print(f"  ingested {res.filename}: {res.status} ({res.chunk_count} chunks)")
        if not container.ingestion.list_documents():
            print("No documents are indexed. Upload some, or pass --ingest-samples.", file=sys.stderr)
            return 2

        cats = [c.strip() for c in args.categories.split(",")] if args.categories else None
        cases = load_cases(settings.eval_questions_path, limit=args.limit, categories=cats)
        print(f"Evaluating {len(cases)} questions | llm={settings.llm_provider}/{settings.resolved_llm_model} "
              f"| judge={container.evaluator.judge.backend} | concurrency={args.concurrency}")

        def progress(res: EvaluationResult, done: int, total: int) -> None:
            ov = "  n/a" if res.overall is None else f"{res.overall:5.2f}"
            print(f"  [{done:>3}/{total}] {ov}  {res.question[:70]}")

        summary = await container.evaluator.evaluate_batch(
            cases, name=args.name, concurrency=args.concurrency, on_progress=progress
        )
        await container.evaluator.drain()
        print("\n" + format_table(summary))
        failed = [r for r in summary.results if r.errors]
        if failed:
            print(f"\n{len(failed)} result(s) had errors (see --json output)")
        if args.json:
            payload = {
                "run_id": summary.run_id, "aggregate": summary.aggregate,
                "by_category": aggregate_by_category(summary.results),
                "results": [r.model_dump() for r in summary.results],
            }
            Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nWrote {args.json}")
        return 0
    finally:
        container.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-evaluate the EKA pipeline on the labelled sample questions.")
    ap.add_argument("--ingest-samples", action="store_true", help="index data/sample_docs first")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N questions")
    ap.add_argument("--categories", default=None, help="comma-separated: standard,paraphrase,keyword")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--name", default="cli run")
    ap.add_argument("--json", default=None, help="write full results to this JSON file")
    args = ap.parse_args(argv)
    settings = get_settings()
    setup_logging("WARNING")
    return asyncio.run(run(settings, args))


if __name__ == "__main__":
    raise SystemExit(main())
