"""Keyword-overlap stand-in for the judge LLM, used by `OfflineLLM` (LLM_PROVIDER=fake).

These are *heuristics*, good enough to exercise the evaluation pipeline end-to-end without an API key.
They are NOT a measure of answer quality - use a real judge model (Groq / OpenAI / Together) for that.
"""
from __future__ import annotations

import json
import re

from app.core.text import tokenize

_CITE = re.compile(r"\[\d+(?:\s*[,;]\s*\d+)*\]")


def _sentences(text: str) -> list[str]:
    text = _CITE.sub("", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 3]


def _overlap(statement: str, haystack_tokens: set[str]) -> float:
    toks = set(tokenize(statement))
    return len(toks & haystack_tokens) / len(toks) if toks else 0.0


def _context_tokens(contexts: list[str]) -> set[str]:
    out: set[str] = set()
    for c in contexts:
        out.update(tokenize(c))
    return out


_REFUSAL = re.compile(r"(could ?n[o']t find|not enough information|no documents|do(?:es)? not (?:contain|know))", re.I)


def offline_judge(task: str, user: str) -> str:
    try:
        payload = json.loads(user)
    except json.JSONDecodeError:
        payload = {}

    if task == "eval_claims":
        answer = payload.get("answer", "")
        claims = [] if _REFUSAL.search(answer) else _sentences(answer)
        return json.dumps({"claims": claims})

    if task == "eval_verify":
        ctx = _context_tokens(payload.get("contexts", []))
        return json.dumps({"verdicts": [
            {"claim": c, "supported": _overlap(c, ctx) >= 0.6, "reason": "keyword overlap"}
            for c in payload.get("claims", [])
        ]})

    if task == "eval_questions":
        answer = payload.get("answer", "")
        if _REFUSAL.search(answer):
            return json.dumps({"questions": [], "noncommittal": True})
        sents = _sentences(answer)[:3] or [answer]
        return json.dumps({"questions": [f"What does the document say about: {s.rstrip('.')}?" for s in sents],
                           "noncommittal": False})

    if task == "eval_ctx_relevance":
        ref = set(tokenize(payload.get("reference", "")))
        return json.dumps({"verdicts": [
            {"index": i, "useful": bool(ref) and len(set(tokenize(c)) & ref) / len(ref) >= 0.3}
            for i, c in enumerate(payload.get("contexts", []), start=1)
        ]})

    if task == "eval_recall":
        ctx = _context_tokens(payload.get("contexts", []))
        return json.dumps({"statements": [
            {"statement": s, "attributed": _overlap(s, ctx) >= 0.6} for s in _sentences(payload.get("reference", ""))
        ]})

    return "{}"
