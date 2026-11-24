"""Exercises the real Ragas metric code with a scripted LLM (no network). Skipped if ragas is not installed."""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.embeddings import FakeEmbedder
from app.evaluation.evaluator import build_judge
from app.evaluation.ragas_adapter import RagasJudge, RagasUnavailableError, ragas_installed

pytestmark = pytest.mark.skipif(not ragas_installed(), reason="ragas not installed (optional dependency)")

CTX = ["Full-time employees receive 20 days of PTO per year.", "Meals are reimbursed up to $75 per day."]


def make_fake_llm(overrides: dict | None = None, calls: list | None = None):
    """A Ragas `InstructorBaseRagasLLM` that answers each internal prompt from canned data keyed by model name."""
    from ragas.llms.base import InstructorBaseRagasLLM

    canned = {
        "StatementGeneratorOutput": {"statements": ["Employees get 20 days of PTO", "Part-time is prorated"]},
        "NLIStatementOutput": {"statements": [
            {"statement": "Employees get 20 days of PTO", "reason": "stated", "verdict": 1},
            {"statement": "Part-time is prorated", "reason": "not in context", "verdict": 0},
        ]},
        "AnswerRelevanceOutput": {"question": "How many PTO days do employees get per year?", "noncommittal": 0},
        "ContextPrecisionOutput": {"reason": "useful", "verdict": 1},
        "ContextRecallOutput": {"classifications": [
            {"statement": "20 days", "reason": "in context 1", "attributed": 1},
            {"statement": "per year", "reason": "in context 1", "attributed": 1},
            {"statement": "carry over", "reason": "missing", "attributed": 0},
        ]},
    } | (overrides or {})

    class FakeRagasLLM(InstructorBaseRagasLLM):
        def __init__(self):
            pass

        async def agenerate(self, prompt, response_model):
            if calls is not None:
                calls.append(response_model.__name__)
            data = canned[response_model.__name__]
            if isinstance(data, Exception):
                raise data
            return response_model.model_validate(data)

        def generate(self, prompt, response_model):
            raise NotImplementedError

    return FakeRagasLLM()


def judge(**kw) -> RagasJudge:
    return RagasJudge(Settings(_env_file=None, llm_provider="fake"), FakeEmbedder(dim=2048), llm=make_fake_llm(**kw))


async def test_all_four_metrics_through_real_ragas_code():
    s = await judge().score("How many PTO days do employees get per year?", "Employees get 20 days of PTO [1].", CTX,
                            ground_truth="20 days per year, can carry over")
    assert s.faithfulness == 0.5  # 1 of 2 statements supported
    assert s.context_precision == 1.0  # every context judged useful
    assert s.context_recall == pytest.approx(2 / 3, abs=1e-3)
    assert s.answer_relevancy is not None and s.answer_relevancy > 0.5  # generated question ~ original question
    assert s.errors == []


async def test_without_ground_truth_recall_is_skipped():
    calls: list[str] = []
    s = await judge(calls=None).score("q?", "an answer", CTX)
    assert s.context_recall is None and s.faithfulness is not None
    j = RagasJudge(Settings(_env_file=None, llm_provider="fake"), FakeEmbedder(dim=64), llm=make_fake_llm(calls=calls))
    await j.score("q?", "an answer", CTX)
    assert "ContextRecallOutput" not in calls


async def test_noncommittal_answer_scores_zero_relevancy():
    s = await judge(overrides={"AnswerRelevanceOutput": {"question": "", "noncommittal": 1}}).score(
        "q?", "I don't know", CTX)
    assert s.answer_relevancy == 0.0


async def test_no_statements_means_faithfulness_not_applicable():
    s = await judge(overrides={"StatementGeneratorOutput": {"statements": []}}).score("q?", "I couldn't find it.", CTX)
    assert s.faithfulness is None  # NaN from Ragas becomes None


async def test_empty_contexts_give_zero_retrieval_scores_without_calling_ragas_on_them():
    calls: list[str] = []
    j = RagasJudge(Settings(_env_file=None, llm_provider="fake"), FakeEmbedder(dim=64), llm=make_fake_llm(calls=calls))
    s = await j.score("q?", "an answer", [], ground_truth="gt")
    assert s.context_precision == 0.0 and s.context_recall == 0.0 and s.faithfulness is None
    assert set(calls) == {"AnswerRelevanceOutput"}  # only answer relevancy ran (it samples 3 questions)


async def test_failing_metric_is_isolated():
    s = await judge(overrides={"ContextPrecisionOutput": RuntimeError("llm timeout")}).score("q?", "ans", CTX, "gt")
    assert s.context_precision is None and s.faithfulness == 0.5
    assert len(s.errors) == 1 and s.errors[0].startswith("context_precision:")


def test_requires_real_llm_unless_injected():
    with pytest.raises(RagasUnavailableError, match="real judge LLM"):
        RagasJudge(Settings(_env_file=None, llm_provider="fake"), FakeEmbedder())
    with pytest.raises(RagasUnavailableError, match="API key"):
        RagasJudge(Settings(_env_file=None, llm_provider="groq", groq_api_key=""), FakeEmbedder())


def test_build_judge_selects_backend():
    from app.core.llm import ScriptedLLM

    custom = build_judge(Settings(_env_file=None, llm_provider="fake"), ScriptedLLM(), FakeEmbedder())
    assert custom.backend == "custom"
    with pytest.raises(RagasUnavailableError):  # backend=ragas + fake provider -> clear, early failure
        build_judge(Settings(_env_file=None, llm_provider="fake", eval_backend="ragas"), ScriptedLLM(), FakeEmbedder())


def test_real_llm_construction_does_not_need_network():
    j = RagasJudge(Settings(_env_file=None, llm_provider="groq", groq_api_key="gsk_test"), FakeEmbedder(dim=64))
    assert j.backend == "ragas" and j.faithfulness is not None
