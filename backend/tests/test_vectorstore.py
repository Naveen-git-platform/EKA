from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore import VectorStore, VectorStoreError, point_id
from app.ingestion.models import Chunk


def mk(i: int, doc: str = "d1") -> Chunk:
    return Chunk(chunk_id=f"{doc}-{i:04d}", doc_id=doc, chunk_index=i, text=f"text {i}", filename=f"{doc}.txt", page=i)


VECS = {0: [1.0, 0.0, 0.0, 0.0], 1: [0.0, 1.0, 0.0, 0.0], 2: [0.0, 0.0, 1.0, 0.0]}


@pytest.fixture
def store():
    s = VectorStore.in_memory(dim=4)
    yield s
    s.close()


def test_upsert_and_nearest_search(store):
    store.upsert([mk(i) for i in range(3)], [VECS[i] for i in range(3)])
    hits = store.search([0.9, 0.1, 0.0, 0.0], top_k=2)
    assert [c.chunk_id for c, _ in hits] == ["d1-0000", "d1-0001"]
    assert hits[0][1] > hits[1][1]
    assert hits[0][0].page == 0 and hits[0][0].text == "text 0"  # payload round-trips into Chunk


def test_upsert_is_idempotent(store):
    chunks, vecs = [mk(0), mk(1)], [VECS[0], VECS[1]]
    store.upsert(chunks, vecs)
    store.upsert(chunks, vecs)
    assert store.count() == 2


def test_point_id_deterministic():
    assert point_id("a-0001") == point_id("a-0001") != point_id("a-0002")


def test_doc_filter_and_delete(store):
    store.upsert([mk(0, "d1"), mk(0, "d2")], [VECS[0], VECS[0]])
    only_d2 = store.search(VECS[0], top_k=5, doc_ids=["d2"])
    assert [c.doc_id for c, _ in only_d2] == ["d2"]
    assert store.count("d1") == 1
    store.delete_document("d1")
    assert store.count() == 1 and store.count("d1") == 0
    store.delete_document("never-existed")  # no error


def test_search_empty_collection(store):
    assert store.search(VECS[0], top_k=3) == []


def test_length_mismatch_raises(store):
    with pytest.raises(VectorStoreError):
        store.upsert([mk(0), mk(1)], [VECS[0]])


def test_empty_upsert_noop(store):
    store.upsert([], [])
    assert store.count() == 0


def test_wrong_dimension_vector_raises(store):
    with pytest.raises(VectorStoreError):
        store.upsert([mk(0)], [[1.0, 2.0]])


def test_dimension_mismatch_on_existing_collection(tmp_path):
    path = str(tmp_path / "q")
    c1 = QdrantClient(path=path)
    VectorStore(c1, "col", dim=8)
    c1.close()
    c2 = QdrantClient(path=path)
    with pytest.raises(VectorStoreError, match="dim 8"):
        VectorStore(c2, "col", dim=16)
    c2.close()


def test_persists_across_reopen(tmp_path):
    path = str(tmp_path / "q")
    c1 = QdrantClient(path=path)
    s1 = VectorStore(c1, "col", dim=4)
    s1.upsert([mk(0)], [VECS[0]])
    c1.close()
    s2 = VectorStore(QdrantClient(path=path), "col", dim=4)
    assert s2.count() == 1
    s2.close()
