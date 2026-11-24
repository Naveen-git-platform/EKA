from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.core.embeddings import FakeEmbedder
from app.core.vectorstore import VectorStore
from app.ingestion.indexer import IngestionService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS = PROJECT_ROOT / "data" / "sample_docs"
EVAL_QUESTIONS = PROJECT_ROOT / "data" / "eval" / "questions.json"
EMBED_DIM = 2048  # large enough that hash-bucket collisions don't blur retrieval tests


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Isolated settings: fake providers and a temp data dir."""
    return Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        qdrant_path=tmp_path / "qdrant",
        llm_provider="fake",
        embedding_provider="fake",
        embedding_dim=EMBED_DIM,
        chunk_size=400,
        chunk_overlap=60,
        eval_questions_path=EVAL_QUESTIONS,
        sample_docs_dir=SAMPLE_DOCS,
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dim=EMBED_DIM)


@pytest.fixture
def vector_store() -> VectorStore:
    store = VectorStore.in_memory(dim=EMBED_DIM)
    yield store
    store.close()


@pytest.fixture
def ingestion(settings, embedder, vector_store) -> IngestionService:
    return IngestionService.from_settings(settings, embedder, vector_store)


@pytest.fixture
def sample_docs_dir() -> Path:
    return SAMPLE_DOCS
