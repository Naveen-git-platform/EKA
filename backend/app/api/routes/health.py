from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.deps import SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    embedding_provider: str
    documents: int | None = None


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep, request: Request) -> HealthResponse:
    container = getattr(request.app.state, "container", None)
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        llm_provider=settings.llm_provider,
        llm_model=settings.resolved_llm_model,
        llm_configured=bool(settings.llm_api_key),
        embedding_provider=settings.embedding_provider,
        documents=len(container.ingestion.list_documents()) if container else None,
    )
