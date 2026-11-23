"""Optional Ragas backend (`EVAL_BACKEND=ragas`), written against the Ragas 0.4 `metrics.collections` API.

Ragas is a heavy, fast-moving dependency, so it is imported lazily and only when selected. The default, fully
tested backend is the custom judge in `metrics.py`, which implements the same four metric definitions. Both
backends return the same `EvalScores`, so the API, store and UI do not care which one produced the numbers.
"""
from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.core.embeddings import Embedder
from app.core.logging import get_logger
from app.evaluation.models import EvalScores

logger = get_logger(__name__)


class RagasUnavailableError(RuntimeError):
    """Ragas is not installed, or cannot be configured with the current settings."""


def ragas_installed() -> bool:
    try:
        import ragas  # noqa: F401
        from ragas.metrics.collections import Faithfulness  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _value(result: Any) -> float | None:
    """MetricResult.value -> float in [0, 1], or None for NaN / missing."""
    v = getattr(result, "value", result)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(max(0.0, min(1.0, f)), 4)


def _make_embeddings(embedder: Embedder):
    """Adapt EKA's `Embedder` to Ragas' `BaseRagasEmbedding` so answer-relevancy uses the same local model."""
    from ragas.embeddings.base import BaseRagasEmbedding

    class EkaEmbeddings(BaseRagasEmbedding):
        def embed_text(self, text: str, **kwargs: Any) -> list[float]:
            return embedder.embed_query(text)

        async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
            return await asyncio.to_thread(embedder.embed_query, text)

    return EkaEmbeddings()


def _make_llm(settings: Settings):
    """Instructor-backed Ragas LLM pointed at the configured OpenAI-compatible provider (Groq/OpenAI/Together)."""
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return llm_factory(settings.resolved_llm_model, provider="openai", client=client)


class RagasJudge:
    backend = "ragas"

    def __init__(self, settings: Settings, embedder: Embedder, *, llm: Any | None = None) -> None:
        """`llm` may be injected (a Ragas `InstructorBaseRagasLLM`); otherwise one is built from `settings`."""
        if not ragas_installed():
            raise RagasUnavailableError(
                "EVAL_BACKEND=ragas needs Ragas 0.4+: pip install 'ragas>=0.4' (also listed in requirements.txt)"
            )
        if llm is None:
            if settings.llm_provider == "fake":
                raise RagasUnavailableError("Ragas needs a real judge LLM; set LLM_PROVIDER to groq/openai/together")
            if not settings.llm_api_key:
                raise RagasUnavailableError(f"No API key configured for '{settings.llm_provider}' (needed by Ragas)")
            llm = _make_llm(settings)
        from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

        self.faithfulness = Faithfulness(llm=llm)
        self.answer_relevancy = AnswerRelevancy(llm=llm, embeddings=_make_embeddings(embedder))
        self.context_precision = ContextPrecision(llm=llm)
        self.context_recall = ContextRecall(llm=llm)

    async def score(
        self, question: str, answer: str, contexts: Sequence[str], ground_truth: str | None = None
    ) -> EvalScores:
        ctx = [c for c in contexts if c and c.strip()]
        reference = ground_truth or answer
        names: list[str] = []
        coros: list[Any] = []

        # Ragas rejects empty contexts; with nothing retrieved the retrieval metrics are 0 by definition.
        if ctx:
            names += ["faithfulness", "context_precision"]
            coros += [
                self.faithfulness.ascore(user_input=question, response=answer, retrieved_contexts=ctx),
                self.context_precision.ascore(user_input=question, reference=reference, retrieved_contexts=ctx),
            ]
            if ground_truth:
                names.append("context_recall")
                coros.append(
                    self.context_recall.ascore(user_input=question, retrieved_contexts=ctx, reference=ground_truth)
                )
        names.append("answer_relevancy")
        coros.append(self.answer_relevancy.ascore(user_input=question, response=answer))

        results = await asyncio.gather(*coros, return_exceptions=True)
        scores = EvalScores()
        if not ctx:
            scores.context_precision = 0.0
            scores.context_recall = 0.0 if ground_truth else None
        for name, res in zip(names, results, strict=True):
            if isinstance(res, BaseException):
                logger.warning("Ragas metric %s failed: %s", name, res)
                scores.errors.append(f"{name}: {res}")
            else:
                setattr(scores, name, _value(res))
        return scores
