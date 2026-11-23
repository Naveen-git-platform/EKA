from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.core.embeddings import EmbeddingError
from app.core.vectorstore import VectorStore
from app.ingestion.indexer import IngestionService
from app.retrieval.hybrid_retriever import (
    HybridRetriever,
    RetrievalError,
    fuse_rrf,
    fuse_weighted,
)
from tests.helpers import CONCEPTS, ConceptEmbedder

# ------------------------------------------------------------------ pure fusion maths


def test_rrf_hand_computed():
    scores = fuse_rrf([["A", "B", "C"], ["B", "D", "A"]], k=60)
    assert math.isclose(scores["A"], 1 / 61 + 1 / 63)
    assert math.isclose(scores["B"], 1 / 62 + 1 / 61)
    assert math.isclose(scores["C"], 1 / 63)
    assert math.isclose(scores["D"], 1 / 62)
    assert sorted(scores, key=scores.get, reverse=True) == ["B", "A", "D", "C"]


def test_rrf_edge_cases():
    assert fuse_rrf([]) == {}
    assert fuse_rrf([[], []]) == {}
    assert fuse_rrf([["X"]], k=10) == {"X": 1 / 11}
    # item present in both lists beats item that is first in only one list
    s = fuse_rrf([["A", "B"], ["C", "B"]], k=60)
    assert s["B"] > s["A"] and s["B"] > s["C"]


def test_weighted_hand_computed():
    vec = {"A": 0.9, "B": 0.5, "C": 0.1}  # min-max -> 1.0, 0.5, 0.0
    bm = {"B": 10.0, "D": 2.0}  # -> 1.0, 0.0
    s = fuse_weighted(vec, bm, 0.5)
    assert math.isclose(s["A"], 0.5) and math.isclose(s["B"], 0.75)
    assert math.isclose(s["C"], 0.0) and math.isclose(s["D"], 0.0)
    assert fuse_weighted(vec, bm, 1.0)["A"] == 1.0 and fuse_weighted(vec, bm, 1.0)["D"] == 0.0
    assert fuse_weighted(vec, bm, 0.0)["B"] == 1.0 and fuse_weighted(vec, bm, 0.0)["A"] == 0.0


def test_weighted_equal_scores_and_empty():
    assert fuse_weighted({"A": 0.3, "B": 0.3}, {}, 1.0) == {"A": 1.0, "B": 1.0}
    assert fuse_weighted({}, {}, 0.5) == {}


# ------------------------------------------------------------------ retriever on a concept corpus


def top_files(results):
    return [r.filename for r in results]


def test_bm25_rescues_exact_identifier_that_vectors_cannot_see(concept_env):
    retriever, _, _ = concept_env
    res = retriever.retrieve("ERR-5031", top_k=3)
    assert res[0].filename == "err5031.txt"
    assert res[0].bm25_rank == 1 and "bm25" in res[0].sources
    # BM25 mode alone must also put the exact match first (ERR-4290 only shares the partial token "err")
    only = retriever.retrieve("ERR-5031", top_k=3, mode="bm25")
    assert top_files(only)[0] == "err5031.txt"
    assert len(only) < 2 or only[0].score > only[1].score
    assert "pto.txt" not in top_files(only)  # unrelated chunks never match by keyword


def test_vectors_rescue_paraphrase_that_bm25_cannot_match(concept_env):
    retriever, _, _ = concept_env
    assert retriever.retrieve("holiday allowance", top_k=3, mode="bm25") == []  # no shared tokens
    hybrid = retriever.retrieve("holiday allowance", top_k=3)
    assert hybrid[0].filename == "pto.txt"
    assert hybrid[0].sources == ["vector"] and hybrid[0].bm25_rank is None
    vec = retriever.retrieve("holiday allowance", top_k=3, mode="vector")
    assert vec[0].filename == "pto.txt"


def test_chunk_found_by_both_methods_scores_highest(concept_env):
    retriever, _, _ = concept_env
    res = retriever.retrieve("password login security", top_k=3)
    assert res[0].filename == "pw.txt"
    assert res[0].vector_rank == 1 and res[0].bm25_rank == 1
    assert res[0].score > (res[1].score if len(res) > 1 else 0)


def test_results_carry_scores_and_metadata(concept_env):
    retriever, _, ids = concept_env
    r = retriever.retrieve("meals reimbursed per day", top_k=1)[0]
    assert r.filename == "meals.txt" and r.doc_id == ids["meals.txt"]
    assert r.chunk_id.startswith(r.doc_id) and "75" in r.text
    assert r.score > 0 and r.vector_score is not None and r.bm25_score is not None
    assert r.metadata["file_type"] == "txt"


def test_top_k_and_ordering(concept_env):
    retriever, _, _ = concept_env
    for k in (1, 2, 5):
        res = retriever.retrieve("days per year employees company", top_k=k)
        assert len(res) <= k
        scores = [r.score for r in res]
        assert scores == sorted(scores, reverse=True)
    a = retriever.retrieve("employees days", top_k=5)
    b = retriever.retrieve("employees days", top_k=5)
    assert [r.chunk_id for r in a] == [r.chunk_id for r in b]


def test_invalid_arguments(concept_env):
    retriever, _, _ = concept_env
    with pytest.raises(ValueError):
        retriever.retrieve("x", top_k=0)
    with pytest.raises(ValueError):
        retriever.retrieve("x", mode="magic")  # type: ignore[arg-type]
    emb = ConceptEmbedder(CONCEPTS)
    with pytest.raises(ValueError):
        HybridRetriever(emb, retriever.vector_store, retriever.bm25, fusion="nope")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        HybridRetriever(emb, retriever.vector_store, retriever.bm25, vector_weight=1.5)


def test_empty_and_blank_query(concept_env):
    retriever, _, _ = concept_env
    assert retriever.retrieve("", top_k=3) == []
    assert retriever.retrieve("   ", top_k=3) == []


def test_empty_index_returns_nothing(settings):
    emb = ConceptEmbedder(CONCEPTS)
    store = VectorStore.in_memory(dim=emb.dim)
    svc = IngestionService.from_settings(settings, emb, store)
    assert HybridRetriever(emb, store, svc.bm25).retrieve("anything at all", top_k=5) == []


def test_doc_filter_applies_to_every_mode(concept_env):
    retriever, _, ids = concept_env
    for mode in ("hybrid", "vector", "bm25"):
        res = retriever.retrieve("ERR-5031 pool", top_k=5, doc_ids=[ids["err4290.txt"]], mode=mode)
        assert all(r.doc_id == ids["err4290.txt"] for r in res), mode
    res = retriever.retrieve("anything", top_k=5, doc_ids=["unknown-doc"])
    assert res == []


def test_deleted_document_is_no_longer_retrieved(concept_env):
    retriever, svc, ids = concept_env
    assert retriever.retrieve("ERR-5031", top_k=1)[0].filename == "err5031.txt"
    svc.delete_document(ids["err5031.txt"])
    assert all(r.filename != "err5031.txt" for r in retriever.retrieve("ERR-5031", top_k=5))


def test_weighted_fusion_mode(concept_env):
    retriever, _, _ = concept_env
    w = HybridRetriever(retriever.embedder, retriever.vector_store, retriever.bm25, fusion="weighted", vector_weight=0.5)
    res = w.retrieve("password login", top_k=3)
    assert res[0].filename == "pw.txt" and 0.0 <= res[0].score <= 1.0
    # weight 0 behaves like pure BM25 ranking
    bm_only = HybridRetriever(retriever.embedder, retriever.vector_store, retriever.bm25, fusion="weighted", vector_weight=0.0)
    assert bm_only.retrieve("ERR-5031", top_k=1)[0].filename == "err5031.txt"


def test_vector_failure_degrades_to_bm25(concept_env, monkeypatch):
    retriever, _, _ = concept_env

    def boom(text):
        raise EmbeddingError("embedding service down")

    monkeypatch.setattr(retriever.embedder, "embed_query", boom)
    res = retriever.retrieve("ERR-5031", top_k=2)  # hybrid -> BM25 only
    assert res and res[0].filename == "err5031.txt" and res[0].vector_rank is None
    with pytest.raises(RetrievalError):
        retriever.retrieve("ERR-5031", top_k=2, mode="vector")
    with pytest.raises(RetrievalError):  # vector down AND no keyword hits -> nothing to return
        retriever.retrieve("holiday allowance", top_k=2)


def test_from_settings(concept_env):
    retriever, svc, _ = concept_env
    s = Settings(_env_file=None, fusion_method="weighted", rrf_k=10, vector_weight=0.8)
    r = HybridRetriever.from_settings(s, retriever.embedder, retriever.vector_store, svc.bm25)
    assert (r.fusion, r.rrf_k, r.vector_weight) == ("weighted", 10, 0.8)
