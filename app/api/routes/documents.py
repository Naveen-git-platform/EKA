"""Document management: upload, list, inspect, delete."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import ContainerDep
from app.api.schemas import DeleteResponse, DocumentInfo, DocumentListResponse, UploadItemResult, UploadResponse
from app.core.logging import get_logger
from app.ingestion.errors import (
    CorruptDocumentError,
    DocumentNotFoundError,
    EmptyDocumentError,
    FileTooLargeError,
    IngestionError,
    UnsupportedFileTypeError,
)

logger = get_logger(__name__)
router = APIRouter(tags=["documents"])

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    UnsupportedFileTypeError: 415,
    FileTooLargeError: 413,
    EmptyDocumentError: 422,
    CorruptDocumentError: 422,
}


def _status_for(exc: Exception) -> int:
    for cls, code in _STATUS_BY_ERROR.items():
        if isinstance(exc, cls):
            return code
    return 500


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(container: ContainerDep, files: list[UploadFile] = File(...)):
    """Upload one or more PDF / DOCX / TXT / Markdown files.

    Returns 200 with per-file results when at least one file was indexed. If every file fails, the response
    carries the status code of the first failure (415 unsupported type, 413 too large, 422 empty/corrupt)
    and the same per-file body.
    """
    max_bytes = container.settings.max_upload_bytes
    results: list[UploadItemResult] = []
    first_failure_status: int | None = None

    for f in files:
        name = f.filename or "unnamed"
        try:
            if not f.filename:
                raise EmptyDocumentError("Uploaded file has no filename")
            data = await f.read(max_bytes + 1)  # never buffer more than limit+1 bytes
            if len(data) > max_bytes:
                raise FileTooLargeError(f"'{name}' exceeds the {container.settings.max_upload_mb} MB upload limit")
            res = await asyncio.to_thread(container.ingestion.ingest_bytes, name, data)
            results.append(UploadItemResult(
                filename=res.filename, status=res.status, doc_id=res.doc_id, chunk_count=res.chunk_count,
                page_count=res.page_count, replaced_doc_id=res.replaced_doc_id,
            ))
        except Exception as exc:  # noqa: BLE001 - every failure becomes a per-file result
            if not isinstance(exc, IngestionError):
                logger.exception("Unexpected error ingesting %s", name)
            results.append(UploadItemResult(
                filename=name, status="failed", error=str(exc) or type(exc).__name__, error_type=type(exc).__name__,
            ))
            if first_failure_status is None:
                first_failure_status = _status_for(exc)
        finally:
            await f.close()

    body = UploadResponse(
        results=results,
        indexed=sum(r.status != "failed" for r in results),
        failed=sum(r.status == "failed" for r in results),
    )
    if body.indexed == 0 and first_failure_status is not None:
        return JSONResponse(status_code=first_failure_status, content=body.model_dump())
    return body


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(container: ContainerDep) -> DocumentListResponse:
    docs = container.ingestion.list_documents()
    return DocumentListResponse(
        documents=[DocumentInfo(**d.model_dump()) for d in docs],
        total=len(docs),
        total_chunks=sum(d.chunk_count for d in docs),
    )


@router.get("/documents/{doc_id}", response_model=DocumentInfo)
def get_document(doc_id: str, container: ContainerDep) -> DocumentInfo:
    try:
        return DocumentInfo(**container.ingestion.get_document(doc_id).model_dump())
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, container: ContainerDep) -> DeleteResponse:
    try:
        await asyncio.to_thread(container.ingestion.delete_document, doc_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeleteResponse(deleted=doc_id)
