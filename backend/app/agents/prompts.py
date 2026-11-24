"""Prompt templates and formatting helpers for the four agents.

NOTE: `OfflineLLM` (app/core/llm.py) parses the `QUESTION:` / `SOURCES:` layout used here, so keep those
section headers stable.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

PLANNER_SYSTEM = """You are the Planner agent of an enterprise knowledge assistant. The assistant answers questions \
using the company's uploaded documents. Decide HOW to search them.

Pick one strategy:
- "direct": a single, focused search is enough.
- "multi_query": the question is broad or ambiguous; use 2-3 differently worded searches (synonyms, likely keywords).
- "decompose": the question has several parts or needs facts from different places; one search per part.

If a conversation history is given, rewrite the question as a fully self-contained "standalone_query" \
(resolve pronouns like "it" / "that policy"). Otherwise repeat the question unchanged.

Respond with ONLY a JSON object:
{"strategy": "direct|multi_query|decompose", "standalone_query": "...", "sub_queries": ["..."], "reasoning": "one sentence"}
Rules: at most 4 sub_queries; each must be a short search query, not an answer."""

CRITIC_SYSTEM = """You are the Critic agent. You check whether retrieved SOURCES are sufficient and relevant to answer \
the QUESTION. Be strict: do not accept sources that merely share topic words but lack the specific facts needed.

Respond with ONLY a JSON object:
{"sufficient": true|false, "relevance": 0.0-1.0, "coverage": 0.0-1.0, "relevant_sources": [source numbers that help],
 "missing_information": "what is still missing, or empty", "rewritten_queries": ["better search queries if insufficient"],
 "reasoning": "one sentence"}
- relevance: how on-topic the sources are. coverage: how much of the question they let you answer.
- If sufficient is false, give 1-2 rewritten_queries that use different keywords than before (never repeat earlier queries)."""

ANSWER_SYSTEM = """You are the Answer agent of an enterprise knowledge assistant. Answer the QUESTION using ONLY the \
numbered SOURCES provided.

Rules:
1. Every factual statement must end with a citation like [1] or [2][3] that refers to the SOURCES numbers.
2. Never use outside knowledge and never invent facts, numbers or sources.
3. If the SOURCES only partly answer the question, answer the supported part and say clearly what is missing.
4. If they do not contain the answer, say you could not find it in the documents.
5. Be concise and direct. Quote exact figures, limits, and names as written in the sources."""


def format_history(history: Sequence[dict[str, str]] | None, max_chars: int = 1200) -> str:
    if not history:
        return ""
    lines = [f"{m['role'].upper()}: {m['content'].strip()}" for m in history if m.get("content")]
    text = "\n".join(lines)
    return text[-max_chars:]


def format_sources(chunks: Sequence[dict[str, Any]]) -> str:
    """Number sources from 1 so the model can cite them as [n]."""
    blocks = []
    for i, c in enumerate(chunks, start=1):
        loc = []
        if c.get("page") is not None:
            loc.append(f"page {c['page']}")
        if c.get("section"):
            loc.append(f"section: {c['section']}")
        where = f" ({', '.join(loc)})" if loc else ""
        blocks.append(f"[{i}] {c.get('filename', 'document')}{where}\n{c['text'].strip()}")
    return "\n\n".join(blocks)


def planner_user(query: str, history: Sequence[dict[str, str]] | None) -> str:
    hist = format_history(history)
    parts = []
    if hist:
        parts.append(f"CONVERSATION HISTORY:\n{hist}\n")
    parts.append(f"QUESTION: {query}")
    return "\n".join(parts)


def critic_user(query: str, chunks: Sequence[dict[str, Any]], used_queries: Sequence[str]) -> str:
    sources = format_sources(chunks) if chunks else "(no sources were retrieved)"
    earlier = "; ".join(f'"{q}"' for q in used_queries) or "(none)"
    return f"QUESTION: {query}\n\nSEARCHES ALREADY TRIED: {earlier}\n\nSOURCES:\n{sources}"


def answer_user(query: str, chunks: Sequence[dict[str, Any]], history: Sequence[dict[str, str]] | None) -> str:
    hist = format_history(history)
    head = f"CONVERSATION HISTORY:\n{hist}\n\n" if hist else ""
    return f"{head}QUESTION: {query}\n\nSOURCES:\n{format_sources(chunks)}"
