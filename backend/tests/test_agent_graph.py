from __future__ import annotations

import json

import pytest

from app.agents.graph import KnowledgeAgent
from app.agents.state import EVENT_TYPES, NO_ANSWER_TEXT
from app.core.llm import LLMError, ScriptedLLM
from app.core.vectorstore import VectorStore
from app.ingestion.indexer import IngestionService
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalError
from tests.helpers import CONCEPTS, ConceptEmbedder


def J(**kw) -> str:
    return json.dumps(kw)


PLAN_DIRECT = J(strategy="direct", standalone_query="how many PTO days", sub_queries=["how many PTO days"], reasoning="simple")
CRIT_OK = J(sufficient=True, relevance=0.9, coverage=0.9, relevant_sources=[1])
CRIT_NO = J(sufficient=False, relevance=0.1, coverage=0.1, rewritten_queries=["vacation allowance"])
ANSWER = "Full-time employees receive 20 days of PTO [1]."


def make_agent(concept_env, settings, scripts, **settings_kw) -> tuple[KnowledgeAgent, ScriptedLLM]:
    retriever, _, _ = concept_env
    llm = ScriptedLLM(scripts)
    for k, v in settings_kw.items():
        setattr(settings, k, v)
    return KnowledgeAgent(llm, retriever, settings), llm


async def events_of(agent, query="how many PTO days", **kw):
    return [e async for e in agent.stream(query, **kw)]


def types(events):
    return [e["type"] for e in events]


def collapse(seq):
    out = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out


# ------------------------------------------------------------------ happy path
async def test_happy_path_event_order_and_content(concept_env, settings):
    agent, llm = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": ANSWER})
    events = await events_of(agent)
    assert collapse(types(events)) == ["plan", "retrieval", "critique", "token", "citations", "done"]
    assert set(types(events)) <= set(EVENT_TYPES)

    plan = events[0]
    assert plan["strategy"] == "direct" and plan["sub_queries"] == ["how many PTO days"]
    retrieval = next(e for e in events if e["type"] == "retrieval")
    assert retrieval["iteration"] == 1 and retrieval["chunks"][0]["filename"] == "pto.txt"
    streamed = "".join(e["text"] for e in events if e["type"] == "token")
    assert streamed.strip() == ANSWER

    cites = next(e for e in events if e["type"] == "citations")
    assert [c["filename"] for c in cites["citations"]] == ["pto.txt"] and "20 days" in cites["citations"][0]["text"]
    done = events[-1]
    assert done["ok"] is True and done["grounded"] is True and done["answer"] == ANSWER
    assert done["iterations"] == 1 and done["errors"] == []
    assert [t["node"] for t in done["trace"]] == ["planner", "retriever", "critic", "answer"]
    assert all(t["ok"] and t["ms"] >= 0 for t in done["trace"])
    assert len(llm.calls_for("answer")) == 1 and llm.calls_for("answer")[0]["stream"] is True


async def test_tokens_are_emitted_incrementally(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": "a b c d e [1]"})
    tokens = [e["text"] for e in await events_of(agent) if e["type"] == "token"]
    assert len(tokens) >= 5 and "".join(tokens).strip() == "a b c d e [1]"


# ------------------------------------------------------------------ re-retrieval loop
async def test_critic_triggers_second_retrieval_with_rewritten_query(concept_env, settings):
    agent, llm = make_agent(concept_env, settings, {
        "planner": J(strategy="direct", standalone_query="time away from work"),
        "critic": [CRIT_NO, CRIT_OK], "answer": ANSWER})
    events = await events_of(agent, "time away from work")
    retrievals = [e for e in events if e["type"] == "retrieval"]
    critiques = [e for e in events if e["type"] == "critique"]
    assert [r["queries"] for r in retrievals] == [["time away from work"], ["vacation allowance"]]
    assert critiques[0]["will_retry"] is True and critiques[1]["will_retry"] is False
    assert collapse(types(events)) == ["plan", "retrieval", "critique", "retrieval", "critique", "token", "citations", "done"]
    assert events[-1]["iterations"] == 2 and events[-1]["ok"] is True
    # second pass found the PTO document through the rewritten query (vector side: "allowance" ~ timeoff)
    assert any(c["filename"] == "pto.txt" for c in retrievals[1]["chunks"])


async def test_loop_is_capped_by_max_retrieval_loops(concept_env, settings):
    counter = {"n": 0}

    def always_insufficient(_msgs):
        counter["n"] += 1
        return J(sufficient=False, relevance=0, coverage=0, rewritten_queries=[f"fresh query {counter['n']}"])

    agent, llm = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": always_insufficient, "answer": ANSWER},
                            max_retrieval_loops=2)
    events = await events_of(agent)
    assert types(events).count("retrieval") == 3  # 1 initial + 2 re-retrievals, then forced to answer
    assert len(llm.calls_for("critic")) == 3
    assert events[-1]["iterations"] == 3 and events[-1]["answer"] == ANSWER  # still answers with what it has


async def test_loops_disabled(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_NO, "answer": ANSWER},
                          max_retrieval_loops=0)
    events = await events_of(agent)
    assert types(events).count("retrieval") == 1 and events[-1]["iterations"] == 1


async def test_repeated_rewrite_stops_the_loop_early(concept_env, settings):
    crit = J(sufficient=False, relevance=0, coverage=0, rewritten_queries=["same words"])
    agent, llm = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": crit, "answer": ANSWER},
                            max_retrieval_loops=5)
    events = await events_of(agent)
    assert types(events).count("retrieval") == 2  # "same words" is tried once, then deemed already-used
    assert len(llm.calls_for("critic")) == 2


async def test_multi_query_plan_runs_every_subquery(concept_env, settings):
    plan = J(strategy="decompose", standalone_query="x", sub_queries=["password rules", "meal reimbursement limit"])
    agent, _ = make_agent(concept_env, settings, {"planner": plan, "critic": J(sufficient=True, relevance=1, coverage=1),
                                                   "answer": "Both covered [1][2]."})
    events = await events_of(agent, "passwords and meals?")
    retrieval = next(e for e in events if e["type"] == "retrieval")
    files = {c["filename"] for c in retrieval["chunks"]}
    assert retrieval["queries"] == ["password rules", "meal reimbursement limit"]
    assert {"pw.txt", "meals.txt"} <= files


# ------------------------------------------------------------------ no / bad context
async def test_empty_index_gives_refusal_without_calling_answer_llm(settings):
    emb = ConceptEmbedder(CONCEPTS)
    store = VectorStore.in_memory(dim=emb.dim)
    svc = IngestionService.from_settings(settings, emb, store)
    llm = ScriptedLLM({"planner": PLAN_DIRECT, "critic": J(sufficient=False, relevance=0, coverage=0), "answer": "SHOULD NOT RUN"})
    agent = KnowledgeAgent(llm, HybridRetriever(emb, store, svc.bm25), settings)
    events = await events_of(agent)
    done = events[-1]
    assert done["answer"] == NO_ANSWER_TEXT and done["ok"] is True and done["grounded"] is False
    assert llm.calls_for("answer") == []
    assert next(e for e in events if e["type"] == "citations")["citations"] == []


async def test_doc_ids_filter_is_enforced(concept_env, settings):
    _, _, ids = concept_env
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": "From meals [1]."})
    events = await events_of(agent, "how many PTO days", doc_ids=[ids["meals.txt"]])
    files = {c["filename"] for c in next(e for e in events if e["type"] == "retrieval")["chunks"]}
    assert files <= {"meals.txt"}


# ------------------------------------------------------------------ failure degradation
async def test_planner_failure_degrades_to_raw_query(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": LLMError("planner down"), "critic": CRIT_OK, "answer": ANSWER})
    events = await events_of(agent, "how many PTO days")
    assert events[0]["type"] == "plan" and events[0]["fallback"] is True
    assert next(e for e in events if e["type"] == "retrieval")["queries"] == ["how many PTO days"]
    done = events[-1]
    assert done["ok"] is True and done["answer"] == ANSWER and any(e.startswith("planner:") for e in done["errors"])


async def test_critic_failure_accepts_context_and_answers(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": LLMError("critic down"), "answer": ANSWER})
    events = await events_of(agent)
    crit = next(e for e in events if e["type"] == "critique")
    assert crit["degraded"] is True and crit["sufficient"] is True and crit["will_retry"] is False
    assert events[-1]["ok"] is True and any(e.startswith("critic:") for e in events[-1]["errors"])


async def test_answer_failure_emits_error_then_done_not_ok(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": LLMError("quota")})
    events = await events_of(agent)
    assert "error" in types(events) and types(events)[-1] == "done"
    err = next(e for e in events if e["type"] == "error")
    assert err["stage"] == "answer" and "quota" in err["message"]
    assert events[-1]["ok"] is False and events[-1]["answer"] == ""


async def test_retrieval_backend_failure_yields_refusal_not_crash(concept_env, settings, monkeypatch):
    agent, llm = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_NO, "answer": "unused"})

    def boom(*a, **k):
        raise RetrievalError("qdrant unreachable")

    monkeypatch.setattr(agent.retriever, "retrieve", boom)
    events = await events_of(agent)
    done = events[-1]
    assert done["answer"] == NO_ANSWER_TEXT and done["ok"] is True
    assert any("retriever:" in e for e in done["errors"])
    assert llm.calls_for("critic") == []  # critic skipped, and no pointless retry loop
    assert types(events).count("retrieval") == 1


async def test_unexpected_node_crash_is_contained_by_guard(concept_env, settings, monkeypatch):
    import app.agents.graph as graph_mod

    class Exploding:
        def __init__(self, *a, **k): ...

        async def __call__(self, state):
            raise RuntimeError("bug in retriever agent")

    monkeypatch.setattr(graph_mod, "RetrieverAgent", Exploding)
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_NO, "answer": "unused"})
    events = await events_of(agent)
    done = events[-1]
    assert done["type"] == "done" and done["answer"] == NO_ANSWER_TEXT
    assert any("unexpected error" in e for e in done["errors"])
    retriever_trace = [t for t in done["trace"] if t["node"] == "retriever"]
    assert retriever_trace and retriever_trace[0]["ok"] is False


async def test_graph_level_failure_still_ends_with_done(concept_env, settings, monkeypatch):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT})

    async def broken_astream(*a, **k):
        raise RuntimeError("langgraph exploded")
        yield  # pragma: no cover  (makes this an async generator)

    monkeypatch.setattr(agent.graph, "astream", broken_astream)
    events = await events_of(agent)
    assert types(events) == ["error", "done"]
    assert events[0]["stage"] == "graph" and events[1]["ok"] is False


# ------------------------------------------------------------------ input handling
@pytest.mark.parametrize("q", ["", "   ", None])
async def test_empty_question_rejected(concept_env, settings, q):
    agent, llm = make_agent(concept_env, settings, {})
    events = await events_of(agent, q)
    assert types(events) == ["error", "done"] and events[1]["ok"] is False and llm.calls == []


async def test_history_is_truncated_and_forwarded(concept_env, settings):
    agent, llm = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": ANSWER},
                            max_history_turns=1)
    history = [{"role": "user", "content": f"old question {i}"} if i % 2 == 0 else {"role": "assistant", "content": f"old answer {i}"}
               for i in range(6)]
    await events_of(agent, history=history)
    planner_prompt = llm.calls_for("planner")[0]["messages"][-1]["content"]
    assert "old answer 5" in planner_prompt and "old question 4" in planner_prompt
    assert "old question 0" not in planner_prompt  # only the last turn (2 messages) kept
    answer_prompt = llm.calls_for("answer")[0]["messages"][-1]["content"]
    assert "old answer 5" in answer_prompt


async def test_top_k_override_limits_context(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": ANSWER})
    events = await events_of(agent, "employees days company", top_k=1)
    assert len(next(e for e in events if e["type"] == "retrieval")["chunks"]) <= 2  # top_k * 2 merge cap


async def test_consumer_can_abandon_the_stream(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": ANSWER})
    gen = agent.stream("how many PTO days")
    first = await gen.__anext__()
    assert first["type"] == "plan"
    await gen.aclose()  # simulates a client disconnecting mid-stream; must not raise


# ------------------------------------------------------------------ run() + visualisation
async def test_run_returns_consolidated_result(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {"planner": PLAN_DIRECT, "critic": CRIT_OK, "answer": ANSWER})
    res = await agent.run("how many PTO days")
    assert res["answer"] == ANSWER and res["ok"] and res["grounded"] and res["iterations"] == 1
    assert res["plan"]["strategy"] == "direct" and res["critique"]["sufficient"] is True
    assert res["contexts"] and all(isinstance(c, str) for c in res["contexts"])
    assert [c["filename"] for c in res["citations"]] == ["pto.txt"]
    assert res["contexts"] == [s["text"] for s in res["sources"]]
    assert "type" not in res["plan"] and res["events"][-1]["type"] == "done"


def test_mermaid_graph_describes_the_agents(concept_env, settings):
    agent, _ = make_agent(concept_env, settings, {})
    mm = agent.mermaid()
    for node in ("planner", "retriever", "critic", "answer"):
        assert node in mm
    assert "graph TD" in mm and "critic -.-> retriever" in mm and "critic -.-> answer" in mm
