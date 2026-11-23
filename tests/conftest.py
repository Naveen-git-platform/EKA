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


@pytest.fixture
def concept_env(settings):
    """Small corpus + semantic ConceptEmbedder: (HybridRetriever, IngestionService, {filename: doc_id})."""
    from app.retrieval.hybrid_retriever import HybridRetriever
    from tests.helpers import CONCEPT_DOCS, CONCEPTS, ConceptEmbedder

    emb = ConceptEmbedder(CONCEPTS)
    store = VectorStore.in_memory(dim=emb.dim)
    svc = IngestionService.from_settings(settings, emb, store)
    ids = {name: svc.ingest_bytes(name, text.encode()).doc_id for name, text in CONCEPT_DOCS.items()}
    yield HybridRetriever(emb, store, svc.bm25), svc, ids
    store.close()


PLAN_JSON = '{"strategy": "direct", "standalone_query": "how many PTO days", "sub_queries": ["how many PTO days"], "reasoning": "simple"}'
CRITIC_OK_JSON = '{"sufficient": true, "relevance": 0.9, "coverage": 0.9, "relevant_sources": [1]}'


@pytest.fixture
def api_env(settings, embedder, vector_store):
    """(TestClient, Container, ScriptedLLM) wired with fakes - no network, no model downloads."""
    from fastapi.testclient import TestClient

    from app.core.container import Container
    from app.core.llm import ScriptedLLM
    from app.main import create_app

    llm = ScriptedLLM({
        "planner": PLAN_JSON,
        "critic": CRITIC_OK_JSON,
        "answer": "Full-time employees receive 20 days of PTO [1].",
    })
    container = Container.build(settings, embedder=embedder, llm=llm, vector_store=vector_store)
    client = TestClient(create_app(settings, container=container))
    return client, container, llm
