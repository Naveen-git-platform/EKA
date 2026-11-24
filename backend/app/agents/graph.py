"""LangGraph assembly: Planner -> Retriever -> Critic -(insufficient)-> Retriever ... -> Answer."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.answerer import AnswerAgent
from app.agents.base import get_emitter
from app.agents.critic import CriticAgent
from app.agents.planner import PlannerAgent, fallback_plan
from app.agents.retriever import RetrieverAgent
from app.agents.state import EVENT_DONE, EVENT_ERROR, EVENT_PLAN, AgentState
from app.core.config import Settings
from app.core.llm import LLMClient
from app.core.logging import get_logger
from app.retrieval.hybrid_retriever import HybridRetriever

logger = get_logger(__name__)

NodeFn = Callable[[AgentState], Awaitable[dict[str, Any]]]


def _guarded(name: str, fn: NodeFn, fallback: Callable[[AgentState, Exception], dict[str, Any]]) -> NodeFn:
    """Wrap an agent so (a) timing lands in the trace and (b) an unexpected bug degrades instead of crashing."""

    async def run(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            update = await fn(state)
            ok = True
        except Exception as exc:  # noqa: BLE001 - agents handle expected failures; this catches the rest
            logger.exception("Agent '%s' crashed", name)
            update = fallback(state, exc)
            update["errors"] = [*update.get("errors", []), f"{name}: unexpected error: {exc}"]
            ok = False
        update["trace"] = [{"node": name, "ms": round((time.perf_counter() - t0) * 1000, 1), "ok": ok}]
        return update

    return run


def _planner_fallback(state: AgentState, exc: Exception) -> dict[str, Any]:
    plan = fallback_plan(state["query"], "internal error")
    get_emitter()({"type": EVENT_PLAN, **plan})
    return {"plan": plan, "standalone_query": plan["standalone_query"], "queries": plan["sub_queries"]}


def _retriever_fallback(state: AgentState, exc: Exception) -> dict[str, Any]:
    return {"retrieval_failed": not state.get("retrieved"), "iteration": state.get("iteration", 0) + 1}


def _critic_fallback(state: AgentState, exc: Exception) -> dict[str, Any]:
    return {
        "critique": {
            "sufficient": bool(state.get("retrieved")), "relevance": 0.5, "coverage": 0.5, "confidence": 0.5,
            "relevant_indices": [], "missing_information": "", "rewritten_queries": [],
            "reasoning": "Critic crashed; accepting context.", "degraded": True,
        },
        "retry": False,
    }


def _answer_fallback(state: AgentState, exc: Exception) -> dict[str, Any]:
    get_emitter()({"type": EVENT_ERROR, "stage": "answer", "message": str(exc)})
    return {"answer": "", "citations": [], "ok": False}


def build_graph(llm: LLMClient, retriever: HybridRetriever, settings: Settings):
    """Compile the multi-agent StateGraph."""
    max_loops = settings.max_retrieval_loops
    g = StateGraph(AgentState)
    g.add_node("planner", _guarded("planner", PlannerAgent(llm), _planner_fallback))
    retriever_agent = RetrieverAgent(retriever, settings.retrieval_top_k)
    g.add_node("retriever", _guarded("retriever", retriever_agent, _retriever_fallback))
    g.add_node("critic", _guarded("critic", CriticAgent(llm, max_loops), _critic_fallback))
    g.add_node("answer", _guarded("answer", AnswerAgent(llm), _answer_fallback))

    g.add_edge(START, "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "critic")

    def route_after_critic(state: AgentState) -> str:
        # `iteration` counts retrieval passes; allow at most `max_loops` re-retrievals.
        if state.get("retry") and state.get("iteration", 0) <= max_loops:
            return "retriever"
        return "answer"

    g.add_conditional_edges("critic", route_after_critic, {"retriever": "retriever", "answer": "answer"})
    g.add_edge("answer", END)
    return g.compile()


class KnowledgeAgent:
    """High-level entry point: owns the compiled graph and exposes streaming + one-shot execution."""

    def __init__(self, llm: LLMClient, retriever: HybridRetriever, settings: Settings) -> None:
        self.llm = llm
        self.retriever = retriever
        self.settings = settings
        self.graph = build_graph(llm, retriever, settings)

    def mermaid(self) -> str:
        """Mermaid source of the agent graph (for docs / visualisation)."""
        return self.graph.get_graph().draw_mermaid()

    async def stream(
        self,
        query: str,
        *,
        history: list[dict[str, str]] | None = None,
        doc_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield typed events: plan, retrieval, critique (xN), token (xN), citations, then done (or error+done)."""
        query = (query or "").strip()
        t0 = time.perf_counter()
        if not query:
            yield {"type": EVENT_ERROR, "stage": "input", "message": "Question must not be empty"}
            yield {"type": EVENT_DONE, "ok": False, "answer": "", "iterations": 0, "elapsed_ms": 0.0,
                   "trace": [], "errors": ["empty question"], "grounded": False}
            return

        max_msgs = self.settings.max_history_turns * 2
        init: AgentState = {
            "query": query,
            "history": (history or [])[-max_msgs:] if max_msgs else [],
            "doc_ids": doc_ids or None,
            "top_k": top_k or self.settings.retrieval_top_k,
            "retrieved": [], "used_queries": [], "iteration": 0, "errors": [], "trace": [],
        }
        final: dict[str, Any] = {}
        failure: str | None = None
        try:
            async for mode, payload in self.graph.astream(
                init, stream_mode=["custom", "values"], config={"recursion_limit": 40}
            ):
                if mode == "custom":
                    yield payload
                else:
                    final = payload
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent graph failed")
            failure = str(exc)
            yield {"type": EVENT_ERROR, "stage": "graph", "message": failure}

        errors = list(final.get("errors", []))
        if failure:
            errors.append(f"graph: {failure}")
        yield {
            "type": EVENT_DONE,
            "ok": bool(final.get("ok")) and failure is None,
            "answer": final.get("answer", ""),
            "iterations": final.get("iteration", 0),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "trace": final.get("trace", []),
            "errors": errors,
            "grounded": bool(final.get("citations")),
        }

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Run to completion and return a consolidated result (used by evaluation and non-streaming callers)."""
        events: list[dict[str, Any]] = []
        async for ev in self.stream(query, **kwargs):
            events.append(ev)
        done = next((e for e in reversed(events) if e["type"] == EVENT_DONE), {})
        by_type: dict[str, dict[str, Any]] = {}
        for e in events:
            by_type[e["type"]] = e  # last one of each type wins (e.g. final critique)
        sources = by_type.get("citations", {}).get("sources", [])
        return {
            "query": query,
            "answer": done.get("answer", ""),
            "ok": done.get("ok", False),
            "grounded": done.get("grounded", False),
            "citations": by_type.get("citations", {}).get("citations", []),
            "sources": sources,
            "contexts": [s["text"] for s in sources],
            "plan": {k: v for k, v in by_type.get("plan", {}).items() if k != "type"},
            "critique": {k: v for k, v in by_type.get("critique", {}).items() if k != "type"},
            "iterations": done.get("iterations", 0),
            "elapsed_ms": done.get("elapsed_ms", 0.0),
            "trace": done.get("trace", []),
            "errors": done.get("errors", []),
            "events": events,
        }
