"""Export the LangGraph agent graph as Mermaid into docs/agent_graph.md.

Usage:  python scripts/export_graph.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.graph import KnowledgeAgent  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.llm import OfflineLLM  # noqa: E402

HEADER = """# Agent graph

Generated from the compiled LangGraph `StateGraph` by `scripts/export_graph.py` (do not edit by hand).

* **planner** - analyses the question, picks `direct` / `multi_query` / `decompose`, rewrites follow-ups into standalone queries.
* **retriever** - runs each planned query through the hybrid (vector + BM25) retriever and merges the results.
* **critic** - judges relevance / sufficiency. If insufficient it proposes new queries and loops back to the retriever
  (at most `MAX_RETRIEVAL_LOOPS` times).
* **answer** - streams a grounded answer with `[n]` citations that refer only to retrieved sources.

"""


def render() -> str:
    settings = Settings(_env_file=None, llm_provider="fake", embedding_provider="fake")
    agent = KnowledgeAgent(OfflineLLM(), None, settings)  # type: ignore[arg-type]  # retriever unused for drawing
    return f"{HEADER}```mermaid\n{agent.mermaid().strip()}\n```\n"


def main() -> None:
    out = ROOT / "docs" / "agent_graph.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
