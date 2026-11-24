"""Retrieval quality on the bundled sample corpus + labelled questions."""
from __future__ import annotations

import pytest

from app.retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk
from app.retrieval.metrics import evaluate_retrieval, evidence_recall, load_questions, reciprocal_rank, relevant_hits
from tests.conftest import EVAL_QUESTIONS, SAMPLE_DOCS


def rc(filename: str, text: str, cid: str = "c") -> RetrievedChunk:
    return RetrievedChunk(chunk_id=cid, doc_id="d", filename=filename, text=text, score=1.0)


Q = {"relevant_docs": ["a.md"], "evidence": ["20 days", "5 days"]}


def test_metric_functions():
    hit = rc("a.md", "Employees get 20  days\nof PTO.", "1")  # whitespace-insensitive match
    miss = rc("b.md", "20 days in the wrong doc", "2")
    other = rc("a.md", "Unrelated paragraph", "3")
    assert relevant_hits([other, miss, hit], Q) == [False, False, True]
    assert reciprocal_rank([other, miss, hit], Q) == pytest.approx(1 / 3)
    assert reciprocal_rank([other, miss], Q) == 0.0
    assert evidence_recall([hit], Q) == 0.5  # only one of two evidence strings found
    assert evidence_recall([hit, rc("a.md", "carry over 5 days")], Q) == 1.0
    assert evidence_recall([miss], Q) == 0.0  # right text, wrong document
    assert evidence_recall([], Q) == 0.0


@pytest.fixture(scope="module")
def loaded_retriever(tmp_path_factory):
    from app.core.config import Settings
    from app.core.embeddings import FakeEmbedder
    from app.core.vectorstore import VectorStore
    from app.ingestion.indexer import IngestionService

    tmp = tmp_path_factory.mktemp("quality")
    settings = Settings(_env_file=None, data_dir=tmp / "data", llm_provider="fake", embedding_provider="fake",
                        embedding_dim=2048, chunk_size=400, chunk_overlap=60)
    emb = FakeEmbedder(dim=2048)
    store = VectorStore.in_memory(dim=2048)
    svc = IngestionService.from_settings(settings, emb, store)
    for f in sorted(SAMPLE_DOCS.iterdir()):
        svc.ingest_path(f)
    yield HybridRetriever(emb, store, svc.bm25)
    store.close()


def test_sample_corpus_retrieval_quality(loaded_retriever):
    qs = load_questions(EVAL_QUESTIONS)
    res = {m: evaluate_retrieval(loaded_retriever, qs, k=5, mode=m) for m in ("vector", "bm25", "hybrid")}
    for m, r in res.items():
        print(m, {k: round(v, 3) for k, v in r.items()})
    assert res["hybrid"]["n_questions"] == len(qs)
    # hybrid must be strong in absolute terms and never worse than the weaker single method
    assert res["hybrid"]["recall@5"] >= 0.9
    assert res["hybrid"]["recall@5"] >= min(res["vector"]["recall@5"], res["bm25"]["recall@5"])
    assert res["hybrid"]["hit_rate@5"] >= 0.9
    assert res["hybrid"]["mrr@5"] >= 0.6


@pytest.mark.slow
def test_real_model_hybrid_retrieval_on_sample_corpus(tmp_path):
    from app.core.config import Settings
    from app.core.embeddings import SentenceTransformerEmbedder
    from app.core.vectorstore import VectorStore
    from app.ingestion.indexer import IngestionService

    settings = Settings(_env_file=None, data_dir=tmp_path / "data", embedding_provider="sentence-transformers",
                        llm_provider="fake", chunk_size=400, chunk_overlap=60)
    emb = SentenceTransformerEmbedder(settings.embedding_model)
    store = VectorStore.in_memory(dim=emb.dim)
    svc = IngestionService.from_settings(settings, emb, store)
    for f in sorted(SAMPLE_DOCS.iterdir()):
        svc.ingest_path(f)
    retriever = HybridRetriever(emb, store, svc.bm25)
    qs = load_questions(EVAL_QUESTIONS)
    res = {m: evaluate_retrieval(retriever, qs, k=5, mode=m) for m in ("vector", "bm25", "hybrid")}
    for m, r in res.items():
        print(m, {k: round(v, 3) for k, v in r.items()})
    assert res["hybrid"]["recall@5"] >= 0.9
    assert res["hybrid"]["hit_rate@5"] >= 0.9
    assert res["hybrid"]["recall@5"] >= min(res["vector"]["recall@5"], res["bm25"]["recall@5"])
    store.close()
