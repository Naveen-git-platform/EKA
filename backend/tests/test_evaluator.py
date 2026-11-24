from __future__ import annotations

import asyncio

import pytest

from app.core.llm import LLMError
from app.evaluation.evaluator import Evaluator, load_cases
from app.evaluation.models import EvalCase, EvalScores
from tests.conftest import EVAL_QUESTIONS

PTO_DOC = b"# Leave\n\n## PTO\nFull-time employees receive 20 days of PTO every year.\n"


@pytest.fixture
def env(api_env):
    client, container, llm = api_env
    container.ingestion.ingest_bytes("handbook.md", PTO_DOC)
    return container.evaluator, container, llm


async def test_evaluate_query_scores_and_persists(env):
    evaluator, container, _ = env
    res = await evaluator.evaluate_query("How many PTO days?", ground_truth="20 days")
    assert res.answer.startswith("Full-time employees") and res.source == "api" and res.backend == "custom"
    assert res.faithfulness == 1.0 and res.context_precision == 1.0 and res.context_recall == 1.0
    assert res.answer_relevancy > 0.5 and res.overall > 0.8 and res.errors == []
    assert res.contexts and "20 days" in res.contexts[0] and res.latency_ms >= 0
    assert container.eval_store.get(res.id) == res


async def test_evaluate_query_without_ground_truth_has_no_recall(env):
    evaluator, _, _ = env
    res = await evaluator.evaluate_query("How many PTO days?")
    assert res.context_recall is None and res.faithfulness is not None


async def test_pipeline_failure_is_recorded_not_scored(env):
    evaluator, container, llm = env
    llm.scripts["answer"] = LLMError("quota")
    llm.calls.clear()
    res = await evaluator.evaluate_query("How many PTO days?")
    assert res.answer == "" and res.faithfulness is None and res.overall is None
    assert res.errors and res.errors[0].startswith("pipeline failed")
    assert llm.calls_for("eval_claims") == []  # judge was not invoked on an empty answer
    assert container.eval_store.count() == 1


async def test_judge_crash_never_propagates(env):
    evaluator, _, _ = env

    class Boom:
        backend = "custom"

        async def score(self, *a, **k):
            raise RuntimeError("judge exploded")

    evaluator.judge = Boom()
    res = await evaluator.evaluate_query("How many PTO days?")
    assert res.faithfulness is None and any("judge exploded" in e for e in res.errors)


async def test_batch_runs_all_cases_and_aggregates(env):
    evaluator, container, _ = env
    cases = [EvalCase(id=f"c{i}", question="How many PTO days?", ground_truth="20 days", category="standard") for i in range(3)]
    progress = []
    summary = await evaluator.evaluate_batch(cases, name="smoke", on_progress=lambda r, d, t: progress.append((d, t)))
    assert summary.total == 3 and summary.completed == 3 and len(summary.results) == 3
    assert sorted(progress) == [(1, 3), (2, 3), (3, 3)]
    assert {r.case_id for r in summary.results} == {"c0", "c1", "c2"} and {r.run_id for r in summary.results} == {summary.run_id}
    assert all(r.source == "batch" and r.category == "standard" for r in summary.results)
    assert summary.aggregate["faithfulness"] == 1.0 and summary.aggregate["count"] == 3.0
    run = container.eval_store.get_run(summary.run_id)
    assert run.status == "completed" and run.completed == 3 and run.name == "smoke"


async def test_batch_respects_concurrency_limit(env):
    evaluator, _, _ = env
    active = {"now": 0, "max": 0}
    original = evaluator.evaluate_query

    async def tracked(*a, **k):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.01)
        try:
            return await original(*a, **k)
        finally:
            active["now"] -= 1

    evaluator.evaluate_query = tracked
    cases = [EvalCase(question="How many PTO days?") for _ in range(6)]
    await evaluator.evaluate_batch(cases, concurrency=2)
    assert active["max"] == 2


async def test_one_crashing_case_does_not_sink_the_batch(env):
    evaluator, container, _ = env
    original = evaluator.evaluate_query

    async def flaky(question, **kw):
        if kw["case"].id == "bad":
            raise RuntimeError("unexpected bug")
        return await original(question, **kw)

    evaluator.evaluate_query = flaky
    cases = [EvalCase(id="ok1", question="How many PTO days?"), EvalCase(id="bad", question="x?"),
             EvalCase(id="ok2", question="How many PTO days?")]
    summary = await evaluator.evaluate_batch(cases)
    assert summary.completed == 3
    bad = next(r for r in summary.results if r.case_id == "bad")
    assert bad.overall is None and "case crashed" in bad.errors[0]
    assert container.eval_store.get_run(summary.run_id).status == "completed"


async def test_start_batch_runs_in_background_and_is_pollable(env):
    evaluator, container, _ = env
    info = evaluator.start_batch([EvalCase(question="How many PTO days?")] * 3, name="bg")
    assert info.status == "running" and info.total == 3
    await evaluator.drain()
    done = container.eval_store.get_run(info.run_id)
    assert done.status == "completed" and done.completed == 3


async def test_schedule_sample_records_auto_result(env):
    evaluator, container, _ = env
    evaluator.schedule_sample("How many PTO days?", "20 days [1]", ["Employees receive 20 days of PTO."], latency_ms=5.0)
    await evaluator.drain()
    [res] = container.eval_store.list()
    assert res.source == "auto" and res.latency_ms == 5.0 and res.faithfulness == 1.0


async def test_background_failure_is_logged_not_raised(env, caplog):
    evaluator, _, _ = env

    async def boom():
        raise RuntimeError("bg failure")

    evaluator._track(boom(), "test")
    await evaluator.drain()
    assert "bg failure" in caplog.text


def test_load_cases_filters():
    all_cases = load_cases(EVAL_QUESTIONS)
    assert len(all_cases) >= 15 and all_cases[0].ground_truth and all_cases[0].id
    assert len(load_cases(EVAL_QUESTIONS, limit=3)) == 3
    only = load_cases(EVAL_QUESTIONS, categories=["standard"])
    assert only and all(c.category == "standard" for c in only)


async def test_evaluate_sample_direct(env):
    evaluator, _, _ = env
    scores = await evaluator.evaluate_sample("How many PTO days?", "20 days [1]", ["20 days of PTO"], "20 days")
    assert isinstance(scores, EvalScores) and scores.context_recall == 1.0


def test_evaluator_is_constructible_with_minimum_concurrency(env):
    evaluator, container, _ = env
    assert Evaluator(container.agent, evaluator.judge, container.eval_store, concurrency=0).concurrency == 1
