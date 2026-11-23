from __future__ import annotations

import json
import math

import pytest

from app.core.embeddings import FakeEmbedder
from app.core.llm import LLMError, ScriptedLLM
from app.evaluation.metrics import (
    JudgeError,
    MetricsJudge,
    context_precision_score,
    context_recall_score,
    cosine,
    faithfulness_score,
)
from app.evaluation.models import EvalScores


def J(**kw) -> str:
    return json.dumps(kw)


CTX = ["Full-time employees receive 20 days of PTO per year.", "Meals are reimbursed up to $75 per day."]


def judge(scripts, dim=2048) -> tuple[MetricsJudge, ScriptedLLM]:
    llm = ScriptedLLM(scripts)
    return MetricsJudge(llm, FakeEmbedder(dim=dim)), llm


# ------------------------------------------------------------------ pure maths
def test_faithfulness_score():
    assert faithfulness_score([True, True]) == 1.0
    assert faithfulness_score([False, False]) == 0.0
    assert faithfulness_score([True, False, True, True]) == 0.75
    assert faithfulness_score([]) is None


def test_context_precision_is_rank_aware_average_precision():
    assert context_precision_score([True, True, True]) == 1.0
    assert context_precision_score([False, False]) == 0.0
    assert context_precision_score([]) == 0.0
    # useful at rank 1 only -> 1/1 ; useful at rank 3 only -> precision@3 = 1/3
    assert context_precision_score([True, False, False]) == 1.0
    assert context_precision_score([False, False, True]) == pytest.approx(1 / 3)
    # [T, F, T]: (1/1 + 2/3) / 2
    assert context_precision_score([True, False, True]) == pytest.approx((1 + 2 / 3) / 2)
    # same hits, better ranking -> higher score
    assert context_precision_score([True, True, False]) > context_precision_score([False, True, True])


def test_context_recall_score():
    assert context_recall_score([True, False]) == 0.5
    assert context_recall_score([]) is None


def test_cosine():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 1], [2, 2]) == pytest.approx(1.0)


# ------------------------------------------------------------------ faithfulness
async def test_faithfulness_all_supported_is_one():
    j, llm = judge({"eval_claims": J(claims=["Employees get 20 days of PTO", "Meals are capped at $75"]),
                    "eval_verify": J(verdicts=[{"claim": "a", "supported": True}, {"claim": "b", "supported": True}])})
    score, unsupported, n = await j.faithfulness("q", "answer", CTX)
    assert (score, unsupported, n) == (1.0, [], 2)
    verify_payload = json.loads(llm.calls_for("eval_verify")[0]["messages"][-1]["content"])
    assert verify_payload["contexts"] == CTX and len(verify_payload["claims"]) == 2


async def test_faithfulness_none_supported_is_zero_and_reports_claims():
    j, _ = judge({"eval_claims": J(claims=["The CEO is Bob", "PTO is 99 days"]),
                  "eval_verify": J(verdicts=[{"supported": False}, {"supported": False}])})
    score, unsupported, _ = await j.faithfulness("q", "a", CTX)
    assert score == 0.0 and unsupported == ["The CEO is Bob", "PTO is 99 days"]


async def test_faithfulness_mixed():
    j, _ = judge({"eval_claims": J(claims=["c1", "c2", "c3", "c4"]),
                  "eval_verify": J(verdicts=[{"supported": True}, {"supported": False}, {"supported": True}, {"supported": True}])})
    score, unsupported, n = await j.faithfulness("q", "a", CTX)
    assert score == 0.75 and unsupported == ["c2"] and n == 4


async def test_faithfulness_no_claims_is_not_applicable():
    j, llm = judge({"eval_claims": J(claims=[])})
    assert await j.faithfulness("q", "I could not find that.", CTX) == (None, [], 0)
    assert llm.calls_for("eval_verify") == []  # nothing to verify


async def test_faithfulness_missing_verdicts_count_as_unsupported():
    j, _ = judge({"eval_claims": J(claims=["c1", "c2", "c3"]), "eval_verify": J(verdicts=[{"supported": True}])})
    score, unsupported, _ = await j.faithfulness("q", "a", CTX)
    assert score == pytest.approx(1 / 3) and unsupported == ["c2", "c3"]  # conservative


async def test_faithfulness_claims_without_contexts_score_zero_without_verifying():
    j, llm = judge({"eval_claims": J(claims=["a fact"])})
    assert await j.faithfulness("q", "a", []) == (0.0, ["a fact"], 1)
    assert llm.calls_for("eval_verify") == []


async def test_faithfulness_bad_judge_output_raises():
    j, _ = judge({"eval_claims": "not json"})
    with pytest.raises(JudgeError, match="valid JSON"):
        await j.faithfulness("q", "a", CTX)
    j2, _ = judge({"eval_claims": J(claims=["c"]), "eval_verify": J(nope=1)})
    with pytest.raises(JudgeError, match="verdicts"):
        await j2.faithfulness("q", "a", CTX)
    j3, _ = judge({"eval_claims": LLMError("down")})
    with pytest.raises(JudgeError, match="LLM call failed"):
        await j3.faithfulness("q", "a", CTX)


# ------------------------------------------------------------------ answer relevancy
async def test_answer_relevancy_high_when_regenerated_questions_match():
    j, _ = judge({"eval_questions": J(questions=["How many PTO days per year?", "How many PTO days per year do employees get?"],
                                      noncommittal=False)})
    high = await j.answer_relevancy("How many PTO days per year do employees get?", "20 days")
    j2, _ = judge({"eval_questions": J(questions=["What is the CEO's favourite colour?", "Who runs the cafeteria?"],
                                       noncommittal=False)})
    low = await j2.answer_relevancy("How many PTO days per year do employees get?", "irrelevant")
    assert 0.5 < high <= 1.0 and low < 0.2 and high > low


async def test_answer_relevancy_zero_for_noncommittal_answers():
    j, _ = judge({"eval_questions": J(questions=["anything"], noncommittal=True)})
    assert await j.answer_relevancy("q", "I don't know") == 0.0


async def test_answer_relevancy_requires_questions():
    j, _ = judge({"eval_questions": J(questions=[], noncommittal=False)})
    with pytest.raises(JudgeError):
        await j.answer_relevancy("q", "a")


# ------------------------------------------------------------------ context precision / recall
async def test_context_precision_from_verdicts():
    j, _ = judge({"eval_ctx_relevance": J(verdicts=[{"index": 1, "useful": True}, {"index": 2, "useful": False},
                                                    {"index": 3, "useful": True}])})
    assert await j.context_precision("q", "ref", ["c1", "c2", "c3"]) == pytest.approx((1 + 2 / 3) / 2)


async def test_context_precision_tolerates_sloppy_verdicts():
    j, _ = judge({"eval_ctx_relevance": J(verdicts=[{"index": "2", "useful": True}, {"index": 99, "useful": True}, "junk"])})
    assert await j.context_precision("q", "ref", ["c1", "c2"]) == pytest.approx(0.5)  # only ctx 2 useful -> 1/2
    assert await j.context_precision("q", "ref", []) == 0.0


async def test_context_recall():
    j, _ = judge({"eval_recall": J(statements=[{"statement": "s1", "attributed": True}, {"statement": "s2", "attributed": False}])})
    assert await j.context_recall("q", "ground truth", CTX) == 0.5
    assert await j.context_recall("q", "ground truth", []) == 0.0
    j2, _ = judge({"eval_recall": J(wrong=[])})
    with pytest.raises(JudgeError):
        await j2.context_recall("q", "gt", CTX)


# ------------------------------------------------------------------ combined score()
def full_scripts():
    return {
        "eval_claims": J(claims=["c1", "c2"]),
        "eval_verify": J(verdicts=[{"supported": True}, {"supported": False}]),
        "eval_questions": J(questions=["How many PTO days?"], noncommittal=False),
        "eval_ctx_relevance": J(verdicts=[{"index": 1, "useful": True}, {"index": 2, "useful": False}]),
        "eval_recall": J(statements=[{"statement": "s", "attributed": True}]),
    }


async def test_score_with_ground_truth_computes_all_four():
    j, llm = judge(full_scripts())
    s = await j.score("How many PTO days?", "answer [1]", CTX, ground_truth="20 days")
    assert s.faithfulness == 0.5 and s.context_precision == 1.0 and s.context_recall == 1.0
    assert s.answer_relevancy > 0.9 and s.errors == [] and s.unsupported_claims == ["c2"] and s.n_claims == 2
    assert 0 <= s.overall <= 1 and s.overall == pytest.approx(sum([0.5, s.answer_relevancy, 1.0, 1.0]) / 4, abs=1e-3)
    ref = json.loads(llm.calls_for("eval_ctx_relevance")[0]["messages"][-1]["content"])["reference"]
    assert ref == "20 days"  # ground truth is the precision reference when available


async def test_score_without_ground_truth_skips_recall_and_uses_answer_as_reference():
    j, llm = judge(full_scripts())
    s = await j.score("q", "the answer", CTX)
    assert s.context_recall is None and llm.calls_for("eval_recall") == []
    ref = json.loads(llm.calls_for("eval_ctx_relevance")[0]["messages"][-1]["content"])["reference"]
    assert ref == "the answer"
    assert s.overall is not None  # mean over the three available metrics


async def test_one_failing_metric_does_not_sink_the_others():
    scripts = full_scripts() | {"eval_questions": LLMError("rate limited")}
    j, _ = judge(scripts)
    s = await j.score("q", "a", CTX, ground_truth="gt")
    assert s.answer_relevancy is None and s.faithfulness == 0.5 and s.context_precision == 1.0
    assert len(s.errors) == 1 and s.errors[0].startswith("answer_relevancy:")


async def test_all_scores_are_bounded():
    j, _ = judge(full_scripts())
    s = await j.score("q", "a", CTX, "gt")
    for m in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        v = getattr(s, m)
        assert v is not None and 0.0 <= v <= 1.0 and not math.isnan(v)


def test_overall_ignores_missing_metrics():
    assert EvalScores().overall is None
    assert EvalScores(faithfulness=1.0, context_precision=0.5).overall == 0.75
