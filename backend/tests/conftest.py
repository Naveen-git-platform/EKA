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
ANSWER_TEXT = "Full-time employees receive 20 days of PTO [1]."

# Scripted judge responses (same ScriptedLLM serves agents and judge in API tests)
EVAL_SCRIPTS = {
    "eval_claims": '{"claims": ["Full-time employees receive 20 days of PTO"]}',
    "eval_verify": '{"verdicts": [{"claim": "x", "supported": true}]}',
    "eval_questions": '{"questions": ["How many PTO days do employees get?"], "noncommittal": false}',
    "eval_ctx_relevance": '{"verdicts": [{"index": 1, "useful": true}]}',
    "eval_recall": '{"statements": [{"statement": "20 days", "attributed": true}]}',
}
