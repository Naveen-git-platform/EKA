"""LLM-as-judge implementations of the four RAG metrics (definitions follow Ragas).

* faithfulness       = supported claims / total claims in the answer
* answer_relevancy   = mean cosine(question, questions regenerated from the answer); 0 for evasive answers
* context_precision  = rank-aware mean precision@k over useful contexts (Ragas' average-precision form)
* context_recall     = attributed reference statements / total reference statements
"""
from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from typing import Any

from app.core.embeddings import Embedder
from app.core.jsonutil import extract_json_object
from app.core.llm import LLMClient
from app.core.logging import get_logger
from app.evaluation import prompts
from app.evaluation.models import EvalScores

logger = get_logger(__name__)

MAX_CONTEXTS = 10
MAX_CONTEXT_CHARS = 1500
MAX_CLAIMS = 20


class JudgeError(RuntimeError):
    """The judge LLM failed or returned something unusable."""


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _prep_contexts(contexts: Sequence[str]) -> list[str]:
    return [c[:MAX_CONTEXT_CHARS] for c in contexts[:MAX_CONTEXTS] if c and c.strip()]


# ---------------------------------------------------------------------------- pure score maths
def faithfulness_score(verdicts: list[bool]) -> float | None:
    return None if not verdicts else sum(verdicts) / len(verdicts)


def context_precision_score(useful: list[bool]) -> float:
    """Average precision: sum_k(precision@k * useful_k) / total_useful. 0.0 when nothing is useful."""
    total = sum(useful)
    if total == 0:
        return 0.0
    hits, acc = 0, 0.0
    for k, u in enumerate(useful, start=1):
        if u:
            hits += 1
            acc += hits / k
    return acc / total


def context_recall_score(attributed: list[bool]) -> float | None:
    return None if not attributed else sum(attributed) / len(attributed)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


# ---------------------------------------------------------------------------- judge
class MetricsJudge:
    def __init__(self, llm: LLMClient, embedder: Embedder) -> None:
        self.llm = llm
        self.embedder = embedder

    async def _ask(self, task: str, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                task=task, json_mode=True, temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 - LLMError and anything the client raises
            raise JudgeError(f"{task}: LLM call failed: {exc}") from exc
        data = extract_json_object(raw)
        if data is None:
            raise JudgeError(f"{task}: judge did not return valid JSON")
        return data

    # ---------------------------------------------------------------- faithfulness
    async def faithfulness(
        self, question: str, answer: str, contexts: Sequence[str]
    ) -> tuple[float | None, list[str], int]:
        """Returns (score or None if the answer makes no claims, unsupported claims, n_claims)."""
        data = await self._ask("eval_claims", prompts.CLAIMS_SYSTEM, {"question": question, "answer": answer})
        claims = [c.strip() for c in data.get("claims", []) if isinstance(c, str) and c.strip()][:MAX_CLAIMS]
        if not claims:
            return None, [], 0
        ctx = _prep_contexts(contexts)
        if not ctx:
            return 0.0, claims, len(claims)  # claims with nothing to ground them
        ver = await self._ask("eval_verify", prompts.VERIFY_SYSTEM, {"claims": claims, "contexts": ctx})
        raw = ver.get("verdicts")
        if not isinstance(raw, list):
            raise JudgeError("eval_verify: missing 'verdicts' list")
        verdicts = [bool(v.get("supported")) if isinstance(v, dict) else False for v in raw]
        # Judge returned the wrong number of verdicts: unmatched claims count as unsupported (conservative).
        verdicts = (verdicts + [False] * len(claims))[: len(claims)]
        unsupported = [c for c, ok in zip(claims, verdicts, strict=True) if not ok]
        return faithfulness_score(verdicts), unsupported, len(claims)

    # ---------------------------------------------------------------- answer relevancy
    async def answer_relevancy(self, question: str, answer: str) -> float:
        data = await self._ask("eval_questions", prompts.QUESTIONS_SYSTEM, {"answer": answer})
        if data.get("noncommittal") is True:
            return 0.0
        gen = [q.strip() for q in data.get("questions", []) if isinstance(q, str) and q.strip()][:5]
        if not gen:
            raise JudgeError("eval_questions: no questions generated")
        vecs = await asyncio.to_thread(self.embedder.embed_documents, [question, *gen])
        sims = [cosine(vecs[0], v) for v in vecs[1:]]
        return _clamp(sum(sims) / len(sims))

    # ---------------------------------------------------------------- context precision
    async def context_precision(self, question: str, reference: str, contexts: Sequence[str]) -> float:
        ctx = _prep_contexts(contexts)
        if not ctx:
            return 0.0
        data = await self._ask("eval_ctx_relevance", prompts.CTX_RELEVANCE_SYSTEM,
                               {"question": question, "reference": reference, "contexts": ctx})
        raw = data.get("verdicts")
        if not isinstance(raw, list):
            raise JudgeError("eval_ctx_relevance: missing 'verdicts' list")
        useful = [False] * len(ctx)
        for pos, v in enumerate(raw):
            if not isinstance(v, dict):
                continue
            try:
                idx = int(v.get("index", pos + 1)) - 1
            except (TypeError, ValueError):
                idx = pos
            if 0 <= idx < len(ctx):
                useful[idx] = bool(v.get("useful"))
        return context_precision_score(useful)

    # ---------------------------------------------------------------- context recall
    async def context_recall(self, question: str, ground_truth: str, contexts: Sequence[str]) -> float | None:
        ctx = _prep_contexts(contexts)
        if not ctx:
            return 0.0  # a reference answer exists but nothing was retrieved to support any of it
        data = await self._ask("eval_recall", prompts.RECALL_SYSTEM,
                               {"question": question, "reference": ground_truth, "contexts": ctx})
        raw = data.get("statements")
        if not isinstance(raw, list):
            raise JudgeError("eval_recall: missing 'statements' list")
        attributed = [bool(s.get("attributed")) if isinstance(s, dict) else False for s in raw]
        return context_recall_score(attributed)

    # ---------------------------------------------------------------- all metrics
    async def score(
        self, question: str, answer: str, contexts: Sequence[str], ground_truth: str | None = None
    ) -> EvalScores:
        """Compute all applicable metrics concurrently. A failing metric becomes None + an error note."""
        reference = ground_truth or answer  # Ragas' reference-free fallback for context precision
        names: list[str] = ["faithfulness", "answer_relevancy", "context_precision"]
        coros = [
            self.faithfulness(question, answer, contexts),
            self.answer_relevancy(question, answer),
            self.context_precision(question, reference, contexts),
        ]
        if ground_truth:
            names.append("context_recall")
            coros.append(self.context_recall(question, ground_truth, contexts))

        results = await asyncio.gather(*coros, return_exceptions=True)
        scores = EvalScores()
        for name, res in zip(names, results, strict=True):
            if isinstance(res, BaseException):
                logger.warning("Metric %s failed: %s", name, res)
                scores.errors.append(f"{name}: {res}")
                continue
            if name == "faithfulness":
                value, unsupported, n_claims = res
                scores.faithfulness = None if value is None else round(_clamp(value), 4)
                scores.unsupported_claims, scores.n_claims = unsupported, n_claims
            else:
                setattr(scores, name, None if res is None else round(_clamp(res), 4))
        return scores
