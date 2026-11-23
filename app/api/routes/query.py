"""Question answering: streaming (SSE) or one-shot JSON."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.agents.state import EVENT_CITATIONS, EVENT_DONE, EVENT_ERROR, EVENT_TOKEN
from app.api.deps import ContainerDep
from app.api.schemas import QueryRequest, QueryResponse
from app.api.sse import SSE_HEADERS, format_sse
from app.core.container import Container
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["query"])

NO_DOCUMENTS_TEXT = "No documents have been uploaded yet. Upload a document first, then ask your question."


def _agent_kwargs(req: QueryRequest) -> dict[str, Any]:
    return {
        "history": [m.model_dump() for m in req.history],
        "doc_ids": req.doc_ids or None,
        "top_k": req.top_k,
    }


async def _events(container: Container, req: QueryRequest) -> AsyncIterator[dict[str, Any]]:
    """Agent events, with a friendly short-circuit when the knowledge base is empty."""
    if not container.ingestion.list_documents():
        yield {"type": EVENT_TOKEN, "text": NO_DOCUMENTS_TEXT}
        yield {"type": EVENT_CITATIONS, "citations": [], "sources": []}
        yield {"type": EVENT_DONE, "ok": True, "answer": NO_DOCUMENTS_TEXT, "iterations": 0, "elapsed_ms": 0.0,
               "trace": [], "errors": [], "grounded": False}
        return
    async for ev in container.agent.stream(req.question, **_agent_kwargs(req)):
        yield ev


@router.post("/query", response_model=None)
async def query(req: QueryRequest, container: ContainerDep):
    """Ask a question. With `stream=true` (default) the response is `text/event-stream`:

    `plan` -> `retrieval` -> `critique` (repeats on re-retrieval) -> `token`* -> `citations` -> `done`
    (an `error` event may appear before `done`). With `stream=false` a single JSON object is returned.
    """
    want_eval = req.evaluate or container.settings.eval_after_query

    if not req.stream:
        result = await container.agent.run(req.question, **_agent_kwargs(req))
        if want_eval and result["ok"] and result["grounded"]:
            container.evaluator.schedule_sample(req.question, result["answer"], result["contexts"],
                                                latency_ms=result["elapsed_ms"])
        return QueryResponse(question=req.question, **{k: result[k] for k in (
            "answer", "ok", "grounded", "citations", "sources", "plan", "critique", "iterations", "elapsed_ms",
            "trace", "errors")})

    final: dict[str, Any] = {}  # what the stream produced; read by the background task afterwards

    async def after_stream() -> None:
        """Runs once the response has been fully sent: optionally score the answer in the background.

        Must be `async`: Starlette runs sync background tasks in a worker thread that has no event loop,
        and scheduling the evaluation task needs the server's loop.
        """
        done = final.get("done")
        if want_eval and done and done.get("ok") and done.get("grounded"):
            sources = final.get("citations", {}).get("sources", [])
            container.evaluator.schedule_sample(req.question, done["answer"], [s["text"] for s in sources],
                                                latency_ms=done.get("elapsed_ms"))

    async def stream() -> AsyncIterator[str]:
        saw_done = False
        try:
            async for ev in _events(container, req):
                saw_done = saw_done or ev["type"] == EVENT_DONE
                if ev["type"] in (EVENT_DONE, EVENT_CITATIONS):
                    final[ev["type"]] = ev
                yield format_sse(ev)
        except Exception as exc:  # noqa: BLE001 - a stream that has started can only report errors in-band
            logger.exception("Streaming query failed")
            yield format_sse({"type": EVENT_ERROR, "stage": "server", "message": str(exc) or type(exc).__name__})
            if not saw_done:
                yield format_sse({"type": EVENT_DONE, "ok": False, "answer": "", "iterations": 0, "elapsed_ms": 0.0,
                                  "trace": [], "errors": [str(exc)], "grounded": False})

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS,
                             background=BackgroundTask(after_stream))
