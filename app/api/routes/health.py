from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    llm_provider: str
    embedding_provider: str


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
    )
