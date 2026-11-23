"""Pure helper functions for the Streamlit UI (no Streamlit imports, so they are trivially unit-testable)."""
from __future__ import annotations

import html
import re
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
METRIC_LABELS = {
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer relevancy",
    "context_precision": "Context precision",
    "context_recall": "Context recall",
    "overall": "Overall",
}
_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_WORD_RE = re.compile(r"[a-z0-9$%][a-z0-9$%.\-_]*", re.IGNORECASE)
_STOP = frozenset(
    "a an and are as at be by for from has have in is it of on or that the their this to was were will with".split()
)


# ------------------------------------------------------------------ scores
def fmt_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def score_level(value: float | None) -> str:
    """'good' >= 0.8, 'ok' >= 0.5, 'bad' below, 'na' when missing."""
    if value is None:
        return "na"
    return "good" if value >= 0.8 else "ok" if value >= 0.5 else "bad"


def score_badge_html(label: str, value: float | None) -> str:
    return f'<span class="eka-badge eka-{score_level(value)}">{html.escape(label)} {fmt_score(value)}</span>'


# ------------------------------------------------------------------ sources & citation highlighting
def location(chunk: dict[str, Any]) -> str:
    parts = [str(chunk.get("filename") or "document")]
    if chunk.get("page") is not None:
        parts.append(f"p.{chunk['page']}")
    if chunk.get("section"):
        parts.append(str(chunk["section"]).split(" > ")[-1])
    return " · ".join(parts)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _tokens(text: str) -> set[str]:
    return {t.lower().rstrip(".") for t in _WORD_RE.findall(text) if t.lower() not in _STOP and len(t) > 1}


def claims_citing(answer: str, index: int) -> list[str]:
    """Sentences of `answer` that carry the citation marker [index], with all markers removed."""
    claims = []
    for sent in split_sentences(answer):
        nums = {int(n) for m in _CITE_RE.findall(sent) for n in re.split(r"[,;]", m)}
        if index in nums:
            claims.append(" ".join(_CITE_RE.sub("", sent).split()))
    return claims


def supporting_spans(source_text: str, answer: str, index: int, min_coverage: float = 0.5) -> list[str]:
    """For each claim that cites source `index`, the source sentence covering most of the claim's key words.

    Coverage = |claim words found in the sentence| / |claim words|; sentences below `min_coverage` are ignored.
    This is an explanation aid for the UI (where does the cited fact live?), not a proof of entailment.
    """
    sentences = [(s, _tokens(s)) for s in split_sentences(source_text)]
    spans: list[str] = []
    for claim in claims_citing(answer, index):
        claim_tokens = _tokens(claim)
        if not claim_tokens:
            continue
        best_cov, best = 0.0, None
        for sent, toks in sentences:
            cov = len(toks & claim_tokens) / len(claim_tokens)
            if cov > best_cov:
                best_cov, best = cov, sent
        if best is not None and best_cov >= min_coverage and best not in spans:
            spans.append(best)
    return spans


def highlight_html(text: str, spans: Sequence[str]) -> str:
    """HTML-escape `text` and wrap each occurrence of a span in <mark>. Safe to render with unsafe_allow_html."""
    ranges: list[tuple[int, int]] = []
    for span in spans:
        start = text.find(span)
        if start != -1:
            ranges.append((start, start + len(span)))
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in ranges:  # drop overlaps
        if merged and s < merged[-1][1]:
            continue
        merged.append((s, e))
    out, pos = [], 0
    for s, e in merged:
        out.append(html.escape(text[pos:s]))
        out.append(f"<mark>{html.escape(text[s:e])}</mark>")
        pos = e
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


# ------------------------------------------------------------------ chat plumbing
def history_for_backend(messages: Sequence[dict[str, Any]], max_messages: int = 12) -> list[dict[str, str]]:
    """Conversation memory: the most recent user/assistant turns, as the API expects them."""
    turns = [{"role": m["role"], "content": m["content"]} for m in messages
             if m.get("role") in ("user", "assistant") and m.get("content")]
    return turns[-max_messages:]


def wait_for_evaluation(
    list_fn: Callable[..., dict[str, Any]],
    question: str,
    known_ids: set[str],
    *,
    timeout: float = 20.0,
    interval: float = 0.75,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any] | None:
    """Poll the evaluation list until a *new* result for `question` appears (auto-evaluation is asynchronous)."""
    deadline = clock() + timeout
    while True:
        for r in list_fn(limit=10).get("results", []):
            if r["id"] not in known_ids and r["question"] == question:
                return r
        if clock() >= deadline:
            return None
        sleep(interval)


# ------------------------------------------------------------------ evaluation tables
def eval_rows(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "time": r["created_at"].replace("T", " ")[:19],
            "question": r["question"],
            "category": r.get("category") or "",
            "faithfulness": r.get("faithfulness"),
            "answer_relevancy": r.get("answer_relevancy"),
            "context_precision": r.get("context_precision"),
            "context_recall": r.get("context_recall"),
            "overall": r.get("overall"),
            "source": r.get("source"),
            "errors": len(r.get("errors") or []),
        }
        for r in results
    ]


def aggregate_by_category(results: Sequence[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[r.get("category") or "uncategorised"].append(r)
    out: dict[str, dict[str, float | None]] = {}
    for cat, rows in sorted(groups.items()):
        agg: dict[str, float | None] = {}
        for m in (*METRICS, "overall"):
            vals = [x[m] for x in rows if x.get(m) is not None]
            agg[m] = round(sum(vals) / len(vals), 3) if vals else None
        agg["n"] = float(len(rows))
        out[cat] = agg
    return out
