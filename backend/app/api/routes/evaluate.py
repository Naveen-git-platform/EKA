"""Evaluation endpoints: evaluate one query, run a batch in the background, browse stored results."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import ContainerDep
from app.api.schemas import BatchEvaluateRequest, EvaluateRequest
from app.core.logging import get_logger
from app.evaluation.evaluator import load_cases
from app.evaluation.models import EvalCase, EvaluationResult, RunInfo

logger = get_logger(__name__)
router = APIRouter(tags=["evaluation"])


class EvaluationListResponse(BaseModel):
    results: list[EvaluationResult]
    total: int
    aggregate: dict[str, float | None]


class RunListResponse(BaseModel):
    runs: list[RunInfo]


@router.post("/evaluate", response_model=EvaluationResult)
async def evaluate_query(req: EvaluateRequest, container: ContainerDep) -> EvaluationResult:
    """Answer `question` with the full agent pipeline, then score the answer (faithfulness, answer relevancy,
    context precision and - when `ground_truth` is given - context recall). The result is stored."""
    if not container.ingestion.list_documents():
        raise HTTPException(status_code=409, detail="No documents indexed yet - upload documents before evaluating")
    return await container.evaluator.evaluate_query(
        req.question, ground_truth=req.ground_truth, top_k=req.top_k, doc_ids=req.doc_ids or None
    )


@router.post("/evaluate/batch", response_model=RunInfo, status_code=202)
async def evaluate_batch(req: BatchEvaluateRequest, container: ContainerDep) -> RunInfo:
    """Start a batch evaluation in the background and return the run immediately; poll `GET /evaluations/runs/{id}`."""
    if not container.ingestion.list_documents():
        raise HTTPException(status_code=409, detail="No documents indexed yet - upload documents before evaluating")
    if req.use_sample:
        path = container.settings.eval_questions_path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Sample question set not found at {path}")
        cases = load_cases(path, limit=req.limit)
    else:
        cases = [EvalCase(question=c.question, ground_truth=c.ground_truth, id=c.id) for c in (req.cases or [])]
        if req.limit:
            cases = cases[: req.limit]
    return container.evaluator.start_batch(cases, name=req.name or ("sample set" if req.use_sample else "custom"),
                                           top_k=req.top_k)


@router.get("/evaluations/runs", response_model=RunListResponse)
def list_runs(container: ContainerDep, limit: int = Query(20, ge=1, le=200)) -> RunListResponse:
    return RunListResponse(runs=container.eval_store.list_runs(limit))


@router.get("/evaluations/runs/{run_id}", response_model=RunInfo)
def get_run(run_id: str, container: ContainerDep) -> RunInfo:
    run = container.eval_store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.get("/evaluations", response_model=EvaluationListResponse)
def list_evaluations(
    container: ContainerDep,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    run_id: str | None = None,
) -> EvaluationListResponse:
    store = container.eval_store
    return EvaluationListResponse(
        results=store.list(limit=limit, offset=offset, run_id=run_id),
        total=store.count(run_id),
        aggregate=store.aggregate(run_id),
    )


@router.get("/evaluations/{eval_id}", response_model=EvaluationResult)
def get_evaluation(eval_id: str, container: ContainerDep) -> EvaluationResult:
    res = container.eval_store.get(eval_id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Evaluation '{eval_id}' not found")
    return res
