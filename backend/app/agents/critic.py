"""Critic agent: judges whether the retrieved context is sufficient and relevant; can trigger re-retrieval."""
from __future__ import annotations

from typing import Any

from app.agents import prompts
from app.agents.base import as_bool, as_unit_float, clean_str_list, get_emitter
from app.agents.state import EVENT_CRITIQUE, AgentState
from app.core.jsonutil import extract_json_object
from app.core.llm import LLMClient, LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_CONFIDENCE = 0.3  # a "sufficient" verdict with lower confidence is treated as insufficient
MAX_REWRITES = 2


def normalize_critique(
    data: dict[str, Any], n_sources: int, used_queries: list[str]
) -> dict[str, Any]:
    """Coerce arbitrary LLM JSON into a consistent critique (never raises)."""
    sufficient = as_bool(data.get("sufficient"), default=False)
    default_score = 1.0 if sufficient else 0.0
    relevance = as_unit_float(data.get("relevance"), default_score)
    coverage = as_unit_float(data.get("coverage"), default_score)
    confidence = round((relevance + coverage) / 2, 3)

    if n_sources == 0:
        sufficient = False
    elif sufficient and confidence < MIN_CONFIDENCE:
        sufficient = False  # contradictory: verdict says yes but scores say no

    raw_idx = data.get("relevant_sources")
    relevant: list[int] = []
    if isinstance(raw_idx, list):
        for i in raw_idx:
            try:
                n = int(i)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= n_sources and n not in relevant:
                relevant.append(n)

    used = {q.lower() for q in used_queries}
    rewrites = [q for q in clean_str_list(data.get("rewritten_queries"), MAX_REWRITES + 2) if q.lower() not in used]
    missing = data.get("missing_information")
    missing = " ".join(missing.split())[:300] if isinstance(missing, str) else ""
    reasoning = data.get("reasoning")
    reasoning = " ".join(reasoning.split())[:300] if isinstance(reasoning, str) else ""
    return {
        "sufficient": sufficient,
        "relevance": relevance,
        "coverage": coverage,
        "confidence": confidence,
        "relevant_indices": relevant,
        "missing_information": missing,
        "rewritten_queries": rewrites[:MAX_REWRITES],
        "reasoning": reasoning,
        "degraded": False,
    }


class CriticAgent:
    def __init__(self, llm: LLMClient, max_loops: int = 2) -> None:
        self.llm = llm
        self.max_loops = max_loops

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        chunks = state.get("retrieved", [])
        used = state.get("used_queries", [])
        iteration = state.get("iteration", 1)
        question = state.get("standalone_query") or state["query"]
        errors: list[str] = []

        if state.get("retrieval_failed") and not chunks:
            critique = {
                "sufficient": False, "relevance": 0.0, "coverage": 0.0, "confidence": 0.0,
                "relevant_indices": [], "missing_information": "retrieval backend failed",
                "rewritten_queries": [], "reasoning": "Retrieval failed; retrying would not help.", "degraded": True,
            }
        else:
            try:
                raw = await self.llm.complete(
                    [
                        {"role": "system", "content": prompts.CRITIC_SYSTEM},
                        {"role": "user", "content": prompts.critic_user(question, chunks, used)},
                    ],
                    task="critic",
                    json_mode=True,
                    temperature=0.0,
                )
                data = extract_json_object(raw)
                if data is None:
                    raise ValueError("critic returned no valid JSON")
                critique = normalize_critique(data, len(chunks), used)
            except (LLMError, ValueError) as exc:
                logger.warning("Critic degraded (accepting context): %s", exc)
                errors.append(f"critic: {exc}")
                critique = {
                    "sufficient": bool(chunks), "relevance": 0.5, "coverage": 0.5, "confidence": 0.5,
                    "relevant_indices": [], "missing_information": "",
                    "rewritten_queries": [], "reasoning": "Critic unavailable; accepting retrieved context.",
                    "degraded": True,
                }

        # --- decide whether to loop back to the retriever -------------------------------------------------
        loops_used = iteration - 1
        next_queries: list[str] = []
        if not critique["sufficient"] and loops_used < self.max_loops and not state.get("retrieval_failed"):
            next_queries = list(critique["rewritten_queries"])
            if not next_queries and critique["missing_information"]:
                cand = critique["missing_information"]
                if cand.lower() not in {q.lower() for q in used}:
                    next_queries = [cand]
        retry = bool(next_queries)

        get_emitter()(
            {
                "type": EVENT_CRITIQUE,
                "iteration": iteration,
                "sufficient": critique["sufficient"],
                "confidence": critique["confidence"],
                "relevance": critique["relevance"],
                "coverage": critique["coverage"],
                "missing_information": critique["missing_information"],
                "rewritten_queries": next_queries,
                "will_retry": retry,
                "reasoning": critique["reasoning"],
                "degraded": critique["degraded"],
            }
        )
        update: dict[str, Any] = {"critique": critique, "retry": retry, "errors": errors}
        if retry:
            update["queries"] = next_queries
        return update
