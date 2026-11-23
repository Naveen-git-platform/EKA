from __future__ import annotations

import json

import pytest

from app.agents.answerer import AnswerAgent, extract_citations, select_context
from app.agents.critic import MAX_REWRITES, CriticAgent, normalize_critique
from app.agents.planner import PlannerAgent, normalize_plan
from app.agents.retriever import RetrieverAgent, merge_chunks
from app.agents.state import NO_ANSWER_TEXT
from app.core.llm import LLMError, ScriptedLLM
from app.retrieval.hybrid_retriever import RetrievalError


def J(**kw) -> str:
    return json.dumps(kw)


def chunk(i: int, score: float = 1.0, text: str | None = None, **kw) -> dict:
    return {"chunk_id": f"c{i}", "doc_id": "d", "filename": f"f{i}.md", "text": text or f"text {i}",
            "score": score, "page": kw.get("page"), "section": kw.get("section"),
            "vector_rank": kw.get("vector_rank"), "bm25_rank": kw.get("bm25_rank")}


# ================================================================== planner
def test_normalize_plan_direct_ignores_extra_subqueries():
    p = normalize_plan({"strategy": "direct", "standalone_query": "pto days?", "sub_queries": ["a", "b"]}, "orig")
    assert p["strategy"] == "direct" and p["sub_queries"] == ["pto days?"] and p["fallback"] is False


def test_normalize_plan_multi_query_keeps_question_first_dedupes_and_caps():
    p = normalize_plan({"strategy": "multi_query", "standalone_query": "Q",
                        "sub_queries": ["q", "a", "b", "c", "d", "e"]}, "orig")
    assert p["sub_queries"] == ["Q", "a", "b", "c"]  # duplicate of Q dropped, capped at 4


def test_normalize_plan_decompose_uses_only_subqueries():
    p = normalize_plan({"strategy": "Decompose", "sub_queries": ["part one", "part two"]}, "orig")
    assert p["strategy"] == "decompose" and p["sub_queries"] == ["part one", "part two"]
    assert p["standalone_query"] == "orig"


def test_normalize_plan_garbage_values():
    p = normalize_plan({"strategy": "telepathy", "standalone_query": 42, "sub_queries": "single string", "reasoning": [1]},
                       "orig")
    assert p["strategy"] == "direct" and p["standalone_query"] == "orig" and p["reasoning"] == ""
    p2 = normalize_plan({"strategy": "decompose", "sub_queries": []}, "orig")
    assert p2["strategy"] == "direct" and p2["sub_queries"] == ["orig"]  # nothing to decompose into


async def test_planner_success_and_prompt_contents():
    llm = ScriptedLLM({"planner": J(strategy="multi_query", standalone_query="parental leave length",
                                     sub_queries=["maternity leave", "paternity leave"], reasoning="broad")})
    history = [{"role": "user", "content": "Tell me about leave"}, {"role": "assistant", "content": "Sure."}]
    out = await PlannerAgent(llm)({"query": "how long is it?", "history": history})
    assert out["plan"]["strategy"] == "multi_query" and out["errors"] == []
    assert out["queries"] == ["parental leave length", "maternity leave", "paternity leave"]
    call = llm.calls_for("planner")[0]
    assert call["json_mode"] is True
    user = call["messages"][-1]["content"]
    assert "CONVERSATION HISTORY" in user and "Tell me about leave" in user and "QUESTION: how long is it?" in user


async def test_planner_code_fenced_json_is_accepted():
    llm = ScriptedLLM({"planner": "```json\n" + J(strategy="direct", standalone_query="x") + "\n```"})
    out = await PlannerAgent(llm)({"query": "x"})
    assert out["plan"]["fallback"] is False


@pytest.mark.parametrize("script", ["I think you should search for it.", "{not json", "", LLMError("rate limited")])
async def test_planner_falls_back_to_raw_query(script):
    out = await PlannerAgent(ScriptedLLM({"planner": script}))({"query": "  my question  "})
    assert out["plan"]["fallback"] is True and out["plan"]["strategy"] == "direct"
    assert out["queries"] == ["my question"]
    assert out["errors"] and out["errors"][0].startswith("planner:")


# ================================================================== critic
def test_normalize_critique_basic_and_clamping():
    c = normalize_critique({"sufficient": "true", "relevance": 7, "coverage": "0.8", "relevant_sources": [2, "1", 9, 2, "x"]},
                           n_sources=3, used_queries=[])
    assert c["sufficient"] is True and c["relevance"] == 1.0 and c["coverage"] == 0.8
    assert c["confidence"] == 0.9 and c["relevant_indices"] == [2, 1]  # out-of-range / duplicates / junk dropped


def test_normalize_critique_consistency_rules():
    assert normalize_critique({"sufficient": True}, 0, [])["sufficient"] is False  # nothing retrieved
    low = normalize_critique({"sufficient": True, "relevance": 0.1, "coverage": 0.1}, 3, [])
    assert low["sufficient"] is False  # verdict contradicts its own scores
    assert normalize_critique({"sufficient": False}, 3, [])["confidence"] == 0.0
    assert normalize_critique({}, 3, [])["sufficient"] is False  # missing verdict -> insufficient


def test_normalize_critique_filters_already_used_rewrites():
    c = normalize_critique({"sufficient": False, "rewritten_queries": ["Used Query", "fresh one", "another", "third"]},
                           2, ["used query"])
    assert c["rewritten_queries"] == ["fresh one", "another"][:MAX_REWRITES]


async def test_critic_sufficient_means_no_retry():
    llm = ScriptedLLM({"critic": J(sufficient=True, relevance=0.9, coverage=0.9, relevant_sources=[1])})
    out = await CriticAgent(llm, max_loops=2)({"query": "q", "retrieved": [chunk(1)], "used_queries": ["q"], "iteration": 1})
    assert out["retry"] is False and out["critique"]["sufficient"] is True and "queries" not in out


async def test_critic_insufficient_triggers_retry_with_new_queries():
    llm = ScriptedLLM({"critic": J(sufficient=False, relevance=0.2, coverage=0.1, rewritten_queries=["better words"])})
    out = await CriticAgent(llm, max_loops=2)({"query": "q", "retrieved": [chunk(1)], "used_queries": ["q"], "iteration": 1})
    assert out["retry"] is True and out["queries"] == ["better words"]


async def test_critic_respects_loop_cap():
    llm = ScriptedLLM({"critic": J(sufficient=False, relevance=0, coverage=0, rewritten_queries=["new"])})
    agent = CriticAgent(llm, max_loops=2)
    st = {"query": "q", "retrieved": [chunk(1)], "used_queries": ["q"]}
    assert (await agent({**st, "iteration": 2}))["retry"] is True  # 1 re-retrieval used, 1 allowed
    assert (await agent({**st, "iteration": 3}))["retry"] is False  # 2 re-retrievals already used
    assert (await CriticAgent(llm, max_loops=0)({**st, "iteration": 1}))["retry"] is False  # loops disabled


async def test_critic_uses_missing_information_when_no_rewrites_but_never_repeats():
    llm = ScriptedLLM({"critic": J(sufficient=False, relevance=0, coverage=0, missing_information="parental leave weeks")})
    agent = CriticAgent(llm, max_loops=2)
    out = await agent({"query": "q", "retrieved": [chunk(1)], "used_queries": ["q"], "iteration": 1})
    assert out["retry"] and out["queries"] == ["parental leave weeks"]
    again = await agent({"query": "q", "retrieved": [chunk(1)], "used_queries": ["q", "Parental Leave Weeks"], "iteration": 2})
    assert again["retry"] is False  # nothing new to try


async def test_critic_empty_retrieval_is_insufficient():
    llm = ScriptedLLM({"critic": J(sufficient=True, relevance=1, coverage=1)})  # an over-optimistic model
    out = await CriticAgent(llm, 2)({"query": "q", "retrieved": [], "used_queries": ["q"], "iteration": 1})
    assert out["critique"]["sufficient"] is False


async def test_critic_skips_llm_when_retrieval_backend_failed():
    llm = ScriptedLLM()
    out = await CriticAgent(llm, 2)({"query": "q", "retrieved": [], "retrieval_failed": True, "iteration": 1})
    assert llm.calls == [] and out["retry"] is False and out["critique"]["degraded"] is True


@pytest.mark.parametrize("script", ["not json at all", LLMError("boom")])
async def test_critic_failure_accepts_context(script):
    out = await CriticAgent(ScriptedLLM({"critic": script}), 2)(
        {"query": "q", "retrieved": [chunk(1)], "used_queries": ["q"], "iteration": 1})
    assert out["critique"]["degraded"] is True and out["critique"]["sufficient"] is True
    assert out["retry"] is False and out["errors"][0].startswith("critic:")


# ================================================================== retriever agent
class StubRetriever:
    def __init__(self, by_query=None, fail_queries=()):
        self.by_query, self.fail_queries, self.calls = by_query or {}, set(fail_queries), []

    def retrieve(self, query, top_k=5, *, doc_ids=None, mode="hybrid"):
        from app.retrieval.hybrid_retriever import RetrievedChunk

        self.calls.append({"query": query, "top_k": top_k, "doc_ids": doc_ids})
        if query in self.fail_queries:
            raise RetrievalError("backend down")
        return [RetrievedChunk(chunk_id=cid, doc_id="d", filename=f"{cid}.md", text=f"text of {cid}", score=s)
                for cid, s in self.by_query.get(query, [])]


def test_merge_chunks_keeps_best_score_orders_and_caps():
    existing = [chunk(1, 0.5), chunk(2, 0.9)]
    merged = merge_chunks(existing, [chunk(1, 0.95), chunk(3, 0.1)], limit=3)
    assert [c["chunk_id"] for c in merged] == ["c1", "c2", "c3"] and merged[0]["score"] == 0.95
    assert [c["chunk_id"] for c in merge_chunks(existing, [chunk(3, 0.99)], limit=2)] == ["c3", "c2"]


async def test_retriever_agent_runs_every_query_and_accumulates():
    stub = StubRetriever({"q1": [("a", 0.5), ("b", 0.4)], "q2": [("b", 0.8), ("c", 0.3)], "q3": [("d", 0.9)]})
    agent = RetrieverAgent(stub, default_top_k=3)
    first = await agent({"query": "q1", "queries": ["q1", "q2"], "doc_ids": ["d1"]})
    assert [c["chunk_id"] for c in first["retrieved"]] == ["b", "a", "c"] and first["iteration"] == 1
    assert first["retrieval_failed"] is False and first["used_queries"] == ["q1", "q2"]
    assert stub.calls[0] == {"query": "q1", "top_k": 3, "doc_ids": ["d1"]}
    second = await agent({"query": "q1", "queries": ["q3"], "retrieved": first["retrieved"],
                          "used_queries": first["used_queries"], "iteration": 1})
    assert second["iteration"] == 2 and second["used_queries"] == ["q1", "q2", "q3"]
    assert second["retrieved"][0]["chunk_id"] == "d"  # new, higher-scoring chunk merged in front


async def test_retriever_agent_failure_modes():
    all_fail = await RetrieverAgent(StubRetriever(fail_queries={"q"}))({"query": "q", "queries": ["q"]})
    assert all_fail["retrieval_failed"] is True and all_fail["retrieved"] == [] and all_fail["errors"]
    partial = await RetrieverAgent(StubRetriever({"ok": [("a", 1.0)]}, fail_queries={"bad"}))(
        {"query": "q", "queries": ["bad", "ok"]})
    assert partial["retrieval_failed"] is False and len(partial["retrieved"]) == 1 and len(partial["errors"]) == 1


async def test_retriever_agent_falls_back_to_standalone_query_and_top_k_override():
    stub = StubRetriever()
    await RetrieverAgent(stub, 5)({"query": "raw", "standalone_query": "standalone", "top_k": 2})
    assert stub.calls == [{"query": "standalone", "top_k": 2, "doc_ids": None}]


# ================================================================== answerer
def test_extract_citations_valid_invalid_and_grouped():
    text = "Fact one [1]. Fact two [2, 3]. Made up [9]. Mixed [1][7]. Again [2]."
    cleaned, cited = extract_citations(text, n_sources=3)
    assert cited == [1, 2, 3]
    assert "[9]" not in cleaned and "[7]" not in cleaned
    assert "Made up." in cleaned and "Mixed [1]." in cleaned and "[2][3]" in cleaned


def test_extract_citations_no_markers():
    assert extract_citations("Plain answer.", 2) == ("Plain answer.", [])


def test_select_context_uses_critic_subset_and_truncates():
    chunks = [chunk(i, text="x" * 3000) for i in range(1, 5)]
    state = {"retrieved": chunks, "critique": {"relevant_indices": [3, 1]}}
    ctx = select_context(state)
    assert [c["chunk_id"] for c in ctx] == ["c3", "c1"] and all(len(c["text"]) == 1500 for c in ctx)
    assert len(select_context({"retrieved": [chunk(i) for i in range(20)]})) == 8  # capped
    assert len(select_context({"retrieved": chunks, "critique": {"relevant_indices": [99]}})) == 4  # invalid -> all


async def test_answerer_cites_only_retrieved_sources():
    llm = ScriptedLLM({"answer": "Employees get 20 days [1]. Part-time is prorated [2]. Invented claim [5]."})
    chunks = [chunk(1, page=3, section="PTO", text="20 days of PTO"), chunk(2, text="prorated"), chunk(3, text="unused")]
    out = await AnswerAgent(llm)({"query": "pto?", "retrieved": chunks})
    assert out["ok"] is True and "[5]" not in out["answer"] and "Invented claim." in out["answer"]
    assert [c["index"] for c in out["citations"]] == [1, 2]  # source 3 was never cited
    first = out["citations"][0]
    assert first["chunk_id"] == "c1" and first["page"] == 3 and first["section"] == "PTO" and first["text"] == "20 days of PTO"
    sent = llm.calls_for("answer")[0]["messages"][-1]["content"]
    assert "[1] f1.md (page 3, section: PTO)" in sent and "[3] f3.md" in sent and "QUESTION: pto?" in sent


async def test_answerer_refuses_without_context_and_never_calls_llm():
    llm = ScriptedLLM()
    out = await AnswerAgent(llm)({"query": "anything", "retrieved": []})
    assert out["answer"] == NO_ANSWER_TEXT and out["citations"] == [] and out["ok"] is True and llm.calls == []


async def test_answerer_respects_critic_relevant_subset_numbering():
    llm = ScriptedLLM({"answer": "Only the second chunk matters [1]."})
    chunks = [chunk(1, text="noise"), chunk(2, text="signal")]
    out = await AnswerAgent(llm)({"query": "q", "retrieved": chunks, "critique": {"relevant_indices": [2]}})
    assert out["citations"][0]["chunk_id"] == "c2"  # [1] refers to the first *selected* source


async def test_answerer_llm_failure_marks_not_ok():
    out = await AnswerAgent(ScriptedLLM({"answer": LLMError("quota exceeded")}))({"query": "q", "retrieved": [chunk(1)]})
    assert out["ok"] is False and out["errors"][0].startswith("answer:") and out["answer"] == ""


async def test_answerer_empty_response_marks_not_ok():
    out = await AnswerAgent(ScriptedLLM({"answer": "   "}))({"query": "q", "retrieved": [chunk(1)]})
    assert out["ok"] is False and "empty" in out["errors"][0]


def test_extract_citations_normalises_cjk_bracket_styles():
    """Regression: gpt-oss (via Groq) writes citations as 【1】 - found in the first live run."""
    text = "Employees accrue 20 days【1】. Parental leave is 16 weeks［2］. Both apply【1，2】. Fake【9】."
    cleaned, cited = extract_citations(text, n_sources=2)
    assert cited == [1, 2]
    assert "【" not in cleaned and "［" not in cleaned and "[9]" not in cleaned
    assert "[1]" in cleaned and "[2]" in cleaned and "[1][2]" in cleaned
