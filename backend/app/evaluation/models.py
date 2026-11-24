from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

METRIC_NAMES = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


class EvalScores(BaseModel):
    """Metric scores in [0, 1]; `None` means "not applicable / could not be computed"."""

    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    # diagnostics
    unsupported_claims: list[str] = Field(default_factory=list)
    n_claims: int | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def overall(self) -> float | None:
        vals = [getattr(self, m) for m in METRIC_NAMES if getattr(self, m) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None


class EvalCase(BaseModel):
    question: str
    ground_truth: str | None = None
    id: str | None = None
    category: str | None = None


class EvaluationResult(BaseModel):
    id: str
    run_id: str | None = None
    created_at: str
    source: Literal["api", "batch", "auto"] = "api"
    backend: str = "custom"
    question: str
    ground_truth: str | None = None
    answer: str
    contexts: list[str] = Field(default_factory=list)
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    overall: float | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    case_id: str | None = None
    category: str | None = None

    def scores_dict(self) -> dict[str, Any]:
        return {m: getattr(self, m) for m in METRIC_NAMES} | {"overall": self.overall}


class RunInfo(BaseModel):
    run_id: str
    created_at: str
    name: str | None = None
    status: Literal["running", "completed", "failed"]
    total: int
    completed: int
    backend: str = "custom"
    aggregate: dict[str, float | None] = Field(default_factory=dict)
