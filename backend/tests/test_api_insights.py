from __future__ import annotations

import json

import pytest

from app.core.vectorstore import VectorStore
from app.ingestion.models import Chunk


def _load_samples(client):
    r = client.post("/samples/load")
    assert r.status_code == 200
    return r.json()


def test_stats_on_empty_system(api_env):
    client, container, _ = api_env
    r = client.get("/insights/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"] == 0 and body["chunks"] == 0
    assert body["evaluation"]["count"] == 0
    assert body["llm_provider"] == "fake"


def test_stats_after_loading_samples(api_env):
    client, container, _ = api_env
    _load_samples(client)
    body = client.get("/insights/stats").json()
    assert body["documents"] == 4
    assert body["chunks"] > 0
    assert set(body["file_types"]) == {"md", "pdf", "txt", "docx"}


def test_stats_includes_benchmark_when_file_exists(api_env, tmp_path):
    client, container, _ = api_env
    path = tmp_path / "bench.json"
    path.write_text(json.dumps({"k": 3, "results": {"hybrid": {"all": {"recall@3": 1.0}}}}), encoding="utf-8")
    container.settings.benchmark_results_path = path
    assert client.get("/insights/stats").json()["benchmark"]["k"] == 3


def test_stats_benchmark_missing_or_corrupt_is_null(api_env, tmp_path):
    client, container, _ = api_env
    container.settings.benchmark_results_path = tmp_path / "nope.json"
    assert client.get("/insights/stats").json()["benchmark"] is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    container.settings.benchmark_results_path = bad
    assert client.get("/insights/stats").json()["benchmark"] is None


def test_map_empty(api_env):
    client, _, _ = api_env
    body = client.get("/insights/map").json()
    assert body["points"] == [] and body["total"] == 0 and body["truncated"] is False


def test_map_has_one_point_per_chunk_with_valid_coords(api_env):
    client, container, _ = api_env
    _load_samples(client)
    body = client.get("/insights/map").json()
    assert len(body["points"]) == body["total"] == container.vector_store.count()
    assert {d["filename"] for d in body["documents"]} == {
        "employee_handbook.md", "incident_runbook.pdf", "product_faq.txt", "security_policy.docx"}
    for p in body["points"]:
        assert all(-1.0 <= p[a] <= 1.0 for a in "xyz")
        assert p["chunk_id"] and p["snippet"]
    assert len(body["explained_variance"]) == 3


def test_map_truncates_to_max_points(api_env):
    client, _, _ = api_env
    _load_samples(client)
    body = client.get("/insights/map", params={"max_points": 3}).json()
    assert len(body["points"]) == 3
    assert body["truncated"] is True and body["total"] > 3


def test_map_filters_by_document(api_env):
    client, _, _ = api_env
    docs = _load_samples(client)["results"]
    doc_id = docs[0]["doc_id"]
    body = client.get("/insights/map", params={"doc_ids": doc_id}).json()
    assert body["points"] and {p["doc_id"] for p in body["points"]} == {doc_id}


def test_map_validates_max_points(api_env):
    client, _, _ = api_env
    assert client.get("/insights/map", params={"max_points": 0}).status_code == 422
    assert client.get("/insights/map", params={"max_points": 99999}).status_code == 422


def test_scroll_vectors_returns_chunks_and_vectors():
    store = VectorStore.in_memory(dim=4)
    chunks = [Chunk(chunk_id=f"d:{i}", doc_id="d", chunk_index=i, text=f"t{i}", filename="f.txt") for i in range(5)]
    store.upsert(chunks, [[float(i), 1.0, 0.0, 0.0] for i in range(5)])
    rows = store.scroll_vectors()
    assert len(rows) == 5
    assert {c.chunk_id for c, _ in rows} == {c.chunk_id for c in chunks}
    assert all(len(v) == 4 for _, v in rows)
    assert len(store.scroll_vectors(limit=2)) == 2
    assert store.scroll_vectors(["other"]) == []
    store.close()


@pytest.mark.parametrize("n", [300])
def test_scroll_vectors_pages_through_more_than_one_batch(n):
    store = VectorStore.in_memory(dim=3)
    chunks = [Chunk(chunk_id=f"d:{i}", doc_id="d", chunk_index=i, text="x", filename="f.txt") for i in range(n)]
    store.upsert(chunks, [[float(i), 0.5, 0.1] for i in range(n)])
    assert len(store.scroll_vectors()) == n
    store.close()
