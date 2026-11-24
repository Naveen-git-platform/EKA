"""Evaluation service: single-response and batch evaluation, persistence, background scheduling."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.graph import KnowledgeAgent
from app.core.config import Settings
from app.core.embeddings import Embedder
from app.core.llm import LLMClient
from app.core.logging import get_logger
from app.evaluation.metrics import MetricsJudge
from app.evaluation.models import EvalCase, EvalScores, EvaluationResult, RunInfo
from app.evaluation.store import EvaluationStore, now_iso

logger = get_logger(__name__)

ProgressFn = Callable[[EvaluationResult, int, int], Awaitable[None] | None]


class Judge(Protocol):
    backend: str

    async def score(
        self, question: str, answer: str, contexts: Sequence[str], ground_truth: str | None = None
    ) -> EvalScores: ...


class CustomJudge(MetricsJudge):
    backend = "custom"


class BatchSummary(BaseModel):
    run_id: str
    total: int
    completed: int
    aggregate: dict[str, float | None]
    results: list[EvaluationResult]


def load_cases(path: str | Path, limit: int | None = None, categories: Sequence[str] | None = None) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = [
        EvalCase(id=q.get("id"), question=q["question"], ground_truth=q.get("ground_truth"), category=q.get("category"))
        for q in raw
        if not categories or q.get("category") in categories
    ]
    return cases[:limit] if limit else cases


def build_judge(settings: Settings, llm: LLMClient, embedder: Embedder) -> Judge:
    if settings.eval_backend == "ragas":
        from app.evaluation.ragas_adapter import RagasJudge

        return RagasJudge(settings, embedder)
    return CustomJudge(llm, embedder)


class Evaluator:
    def __init__(
        self, agent: KnowledgeAgent, judge: Judge, store: EvaluationStore, *, concurrency: int = 2
    ) -> None:
        self.agent = agent
        self.judge = judge
        self.store = store
        self.concurrency = max(1, concurrency)
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ building blocks
    def _result(
        self, *, question: str, answer: str, contexts: list[str], scores: EvalScores, ground_truth: str | None,
        source: str, run_id: str | None, latency_ms: float | None, case: EvalCase | None, extra_errors: list[str],
    ) -> EvaluationResult:
        return EvaluationResult(
            id=uuid.uuid4().hex[:16], run_id=run_id, created_at=now_iso(), source=source,  # type: ignore[arg-type]
            backend=self.judge.backend,
            question=question, ground_truth=ground_truth, answer=answer, contexts=contexts,
            faithfulness=scores.faithfulness, answer_relevancy=scores.answer_relevancy,
            context_precision=scores.context_precision, context_recall=scores.context_recall, overall=scores.overall,
            unsupported_claims=scores.unsupported_claims, errors=[*extra_errors, *scores.errors], latency_ms=latency_ms,
            case_id=case.id if case else None, category=case.category if case else None,
        )

    async def evaluate_sample(
        self, question: str, answer: str, contexts: Sequence[str], ground_truth: str | None = None
    ) -> EvalScores:
        """Score an already-produced (question, answer, contexts) triple. Never raises."""
        try:
            return await self.judge.score(question, answer, list(contexts), ground_truth)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Judge crashed")
            return EvalScores(errors=[f"judge: {exc}"])

    async def record_sample(
        self, question: str, answer: str, contexts: Sequence[str], *, ground_truth: str | None = None,
        source: str = "auto", run_id: str | None = None, latency_ms: float | None = None, case: EvalCase | None = None,
        extra_errors: list[str] | None = None,
    ) -> EvaluationResult:
        scores = await self.evaluate_sample(question, answer, contexts, ground_truth)
        result = self._result(question=question, answer=answer, contexts=list(contexts), scores=scores,
                              ground_truth=ground_truth, source=source, run_id=run_id, latency_ms=latency_ms,
                              case=case, extra_errors=extra_errors or [])
        self.store.add(result)
        return result

    async def evaluate_query(
        self, question: str, *, ground_truth: str | None = None, top_k: int | None = None,
        doc_ids: list[str] | None = None, source: str = "api", run_id: str | None = None, case: EvalCase | None = None,
    ) -> EvaluationResult:
        """Run the full agent on `question`, then judge its answer + retrieved contexts, and persist the result."""
        run = await self.agent.run(question, top_k=top_k, doc_ids=doc_ids)
        if not run["ok"] or not run["answer"]:
            # The pipeline itself failed: record that instead of scoring an empty answer.
            reason = "; ".join(run["errors"] or ["no answer produced"])
            result = self._result(question=question, answer=run["answer"], contexts=run["contexts"],
                                  scores=EvalScores(), ground_truth=ground_truth, source=source, run_id=run_id,
                                  latency_ms=run["elapsed_ms"], case=case, extra_errors=[f"pipeline failed: {reason}"])
            self.store.add(result)
            return result
        return await self.record_sample(
            question, run["answer"], run["contexts"], ground_truth=ground_truth, source=source, run_id=run_id,
            latency_ms=run["elapsed_ms"], case=case,
        )

    # ------------------------------------------------------------------ batch
    async def evaluate_batch(
        self, cases: Sequence[EvalCase], *, name: str | None = None, run_id: str | None = None,
        top_k: int | None = None, concurrency: int | None = None, on_progress: ProgressFn | None = None,
        create_run: bool = True,
    ) -> BatchSummary:
        run_id = run_id or uuid.uuid4().hex[:12]
        if create_run:
            self.store.create_run(run_id, len(cases), name=name, backend=self.judge.backend)
        sem = asyncio.Semaphore(concurrency or self.concurrency)
        done = 0
        results: list[EvaluationResult | None] = [None] * len(cases)

        async def one(i: int, case: EvalCase) -> None:
            nonlocal done
            async with sem:
                try:
                    res = await self.evaluate_query(case.question, ground_truth=case.ground_truth, top_k=top_k,
                                                    source="batch", run_id=run_id, case=case)
                except Exception as exc:  # noqa: BLE001 - one bad case must not sink the batch
                    logger.exception("Case %s failed", case.id)
                    res = self._result(question=case.question, answer="", contexts=[], scores=EvalScores(),
                                       ground_truth=case.ground_truth, source="batch", run_id=run_id, latency_ms=None,
                                       case=case, extra_errors=[f"case crashed: {exc}"])
                    self.store.add(res)
                results[i] = res
                done += 1
                if on_progress:
                    maybe = on_progress(res, done, len(cases))
                    if asyncio.iscoroutine(maybe):
                        await maybe

        try:
            await asyncio.gather(*(one(i, c) for i, c in enumerate(cases)))
            self.store.finish_run(run_id, "completed")
        except BaseException:
            self.store.finish_run(run_id, "failed")
            raise
        return BatchSummary(
            run_id=run_id, total=len(cases), completed=done, aggregate=self.store.aggregate(run_id),
            results=[r for r in results if r is not None],
        )

    # ------------------------------------------------------------------ background work
    def _track(self, coro: Coroutine[Any, Any, Any], label: str) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.error("Background evaluation '%s' failed: %s", label, t.exception())

        task.add_done_callback(_done)
        return task

    def start_batch(self, cases: Sequence[EvalCase], *, name: str | None = None, top_k: int | None = None) -> RunInfo:
        """Create a run and process it in the background; poll `store.get_run(run_id)` for progress."""
        run_id = uuid.uuid4().hex[:12]
        self.store.create_run(run_id, len(cases), name=name, backend=self.judge.backend)
        self._track(self.evaluate_batch(cases, run_id=run_id, top_k=top_k, create_run=False), f"batch:{run_id}")
        info = self.store.get_run(run_id)
        assert info is not None
        return info

    def schedule_sample(
        self, question: str, answer: str, contexts: Sequence[str], *, latency_ms: float | None = None
    ) -> None:
        """Fire-and-forget evaluation of a live answer (used after /query when evaluation is enabled)."""
        self._track(self.record_sample(question, answer, contexts, source="auto", latency_ms=latency_ms), "auto")

    async def drain(self) -> None:
        """Wait for all background evaluations (used in tests and on shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
