"""Planner agent: analyses the question and decides the retrieval strategy."""
from __future__ import annotations

from typing import Any

from app.agents import prompts
from app.agents.base import clean_str_list, get_emitter
from app.agents.state import EVENT_PLAN, AgentState
from app.core.jsonutil import extract_json_object
from app.core.llm import LLMClient, LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

STRATEGIES = ("direct", "multi_query", "decompose")
MAX_SUBQUERIES = 4


def fallback_plan(query: str, reason: str) -> dict[str, Any]:
    return {
        "strategy": "direct",
        "standalone_query": query,
        "sub_queries": [query],
        "reasoning": f"Planner unavailable ({reason}); searching with the question as written.",
        "fallback": True,
    }


def normalize_plan(data: dict[str, Any], query: str) -> dict[str, Any]:
    """Coerce arbitrary LLM JSON into a valid plan (never raises)."""
    strategy = str(data.get("strategy", "direct")).strip().lower().replace("-", "_").replace(" ", "_")
    if strategy not in STRATEGIES:
        strategy = "direct"
    standalone = data.get("standalone_query")
    standalone = " ".join(standalone.split())[:500] if isinstance(standalone, str) and standalone.strip() else query
    subs = clean_str_list(data.get("sub_queries"), MAX_SUBQUERIES)

    if strategy == "direct":
        queries = [standalone]
    elif not subs:  # multi_query / decompose without any sub-queries degrades to a direct search
        strategy = "direct"
        queries = [standalone]
    elif strategy == "multi_query":
        queries = clean_str_list([standalone, *subs], MAX_SUBQUERIES)  # always keep the full question first
    else:  # decompose
        queries = subs
    reasoning = data.get("reasoning")
    return {
        "strategy": strategy,
        "standalone_query": standalone,
        "sub_queries": queries,
        "reasoning": " ".join(reasoning.split())[:300] if isinstance(reasoning, str) else "",
        "fallback": False,
    }


class PlannerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        query = state["query"].strip()
        errors: list[str] = []
        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": prompts.PLANNER_SYSTEM},
                    {"role": "user", "content": prompts.planner_user(query, state.get("history"))},
                ],
                task="planner",
                json_mode=True,
                temperature=0.0,
            )
            data = extract_json_object(raw)
            if data is None:
                raise ValueError("planner returned no valid JSON")
            plan = normalize_plan(data, query)
        except (LLMError, ValueError) as exc:
            logger.warning("Planner degraded: %s", exc)
            plan = fallback_plan(query, str(exc)[:120])
            errors.append(f"planner: {exc}")

        get_emitter()({"type": EVENT_PLAN, **plan})
        return {
            "plan": plan,
            "standalone_query": plan["standalone_query"],
            "queries": plan["sub_queries"],
            "errors": errors,
        }
