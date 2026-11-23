"""Answer agent: generates the final grounded answer with citations, streaming tokens as they arrive."""
from __future__ import annotations

import re
from typing import Any

from app.agents import prompts
from app.agents.base import get_emitter
from app.agents.state import EVENT_CITATIONS, EVENT_ERROR, EVENT_TOKEN, NO_ANSWER_TEXT, AgentState, chunk_summary
from app.core.llm import LLMClient, LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_CONTEXT_CHUNKS = 8
MAX_CHUNK_CHARS = 1500
_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def select_context(state: AgentState) -> list[dict[str, Any]]:
    """Chunks the answer is allowed to use: the critic's relevant subset if given, else everything retrieved."""
    chunks = list(state.get("retrieved", []))
    wanted = (state.get("critique") or {}).get("relevant_indices") or []
    if wanted:
        subset = [chunks[i - 1] for i in wanted if 1 <= i <= len(chunks)]
        if subset:
            chunks = subset
    out = []
    for c in chunks[:MAX_CONTEXT_CHUNKS]:
        c = dict(c)
        c["text"] = c["text"][:MAX_CHUNK_CHARS]
        out.append(c)
    return out


def extract_citations(answer: str, n_sources: int) -> tuple[str, list[int]]:
    """Return (answer with invalid citation numbers removed, valid cited source numbers in order of appearance)."""
    cited: list[int] = []

    def repl(m: re.Match[str]) -> str:
        nums = [int(x) for x in re.split(r"[,;]", m.group(1))]
        valid = [n for n in nums if 1 <= n <= n_sources]
        for n in valid:
            if n not in cited:
                cited.append(n)
        return "".join(f"[{n}]" for n in valid)  # hallucinated numbers vanish; empty -> marker removed

    cleaned = _CITE_RE.sub(repl, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned).strip()
    return cleaned, cited


def build_citation(index: int, chunk: dict[str, Any]) -> dict[str, Any]:
    summary = chunk_summary(chunk)
    return {
        "index": index,
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk.get("doc_id"),
        "filename": chunk.get("filename"),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "score": summary["score"],
        "snippet": summary["snippet"],
        "text": chunk["text"],
    }


class AnswerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        emit = get_emitter()
        question = state.get("standalone_query") or state["query"]
        context = select_context(state)

        # Nothing retrieved -> refuse deterministically instead of letting a model guess.
        if not context:
            emit({"type": EVENT_TOKEN, "text": NO_ANSWER_TEXT})
            emit({"type": EVENT_CITATIONS, "citations": [], "sources": []})
            return {"answer": NO_ANSWER_TEXT, "citations": [], "ok": True, "errors": []}

        messages = [
            {"role": "system", "content": prompts.ANSWER_SYSTEM},
            {"role": "user", "content": prompts.answer_user(question, context, state.get("history"))},
        ]
        parts: list[str] = []
        errors: list[str] = []
        ok = True
        try:
            async for token in self.llm.stream(messages, task="answer", temperature=0.1):
                parts.append(token)
                emit({"type": EVENT_TOKEN, "text": token})
        except LLMError as exc:
            ok = False
            msg = f"answer: {exc}"
            logger.error("Answer generation failed: %s", exc)
            errors.append(msg)
            emit({"type": EVENT_ERROR, "stage": "answer", "message": str(exc)})

        raw = "".join(parts)
        if ok and not raw.strip():
            ok = False
            errors.append("answer: the model returned an empty response")
            emit({"type": EVENT_ERROR, "stage": "answer", "message": "The model returned an empty response"})
        answer, cited = extract_citations(raw, len(context))
        sources = [build_citation(i, c) for i, c in enumerate(context, start=1)]
        citations = [s for s in sources if s["index"] in cited]
        emit({"type": EVENT_CITATIONS, "citations": citations, "sources": sources})
        return {"answer": answer, "citations": citations, "ok": ok and bool(answer), "errors": errors}
