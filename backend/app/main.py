"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting %s v%s (env=%s)", settings.app_name, settings.app_version, settings.app_env)
        yield
        logger.info("Shutting down %s", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multi-agent RAG over your documents: hybrid retrieval, LangGraph agents, streaming answers.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Make the supplied settings the ones injected into routes.
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


def _default_app() -> FastAPI:
    return create_app()


# `uvicorn app.main:app` - services are built lazily in the lifespan, so importing this module is cheap.
app = _default_app()
