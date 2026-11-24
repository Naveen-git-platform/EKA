from __future__ import annotations

import math

import httpx
import pytest

from app.core.config import Settings
from app.core.embeddings import (
    Embedder,
    EmbeddingError,
    FakeEmbedder,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    build_embedder,
)


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_is_deterministic_normalized_and_sized():
    e = FakeEmbedder(dim=128)
    v1, v2 = e.embed_query("vacation policy"), e.embed_query("vacation policy")
    assert v1 == v2 and len(v1) == 128 == e.dim
    assert math.isclose(sum(x * x for x in v1), 1.0, rel_tol=1e-9)
    assert e.embed_documents(["a b", "c d"]) == [e.embed_query("a b"), e.embed_query("c d")]


def test_fake_similarity_reflects_shared_words():
    e = FakeEmbedder(dim=512)
    q = e.embed_query("database connection pool exhausted")
    related = e.embed_query("the database connection pool is exhausted again")
    unrelated = e.embed_query("parental leave for new parents")
    assert cos(q, related) > cos(q, unrelated)


def test_fake_synonyms_make_paraphrases_close():
    # large dim so unrelated words are very unlikely to share a hash bucket
    plain = FakeEmbedder(dim=65536)
    syn = FakeEmbedder(dim=65536, synonyms={"holiday": "vacation", "leave": "vacation", "time-off": "vacation"})
    a, b = "paid vacation days", "holiday allowance"
    assert cos(plain.embed_query(a), plain.embed_query(b)) == 0.0
    assert cos(syn.embed_query(a), syn.embed_query(b)) > 0.3


def test_fake_handles_empty_text():
    v = FakeEmbedder(dim=16).embed_query("")
    assert len(v) == 16 and math.isclose(sum(x * x for x in v), 1.0)


def test_fake_satisfies_protocol():
    assert isinstance(FakeEmbedder(), Embedder)


def test_build_embedder_variants():
    assert isinstance(build_embedder(Settings(_env_file=None, embedding_provider="fake", embedding_dim=32)), FakeEmbedder)
    st = build_embedder(Settings(_env_file=None, embedding_provider="sentence-transformers"))
    assert isinstance(st, SentenceTransformerEmbedder)  # lazy: model not loaded yet
    assert st._model is None
    oa = build_embedder(Settings(_env_file=None, embedding_provider="openai", openai_api_key="k", embedding_dim=384))
    assert isinstance(oa, OpenAIEmbedder) and oa.dim == 384


def test_openai_requires_key():
    with pytest.raises(EmbeddingError):
        OpenAIEmbedder("")


def test_openai_embedder_request_and_ordering(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        # return out of order to verify sorting by index
        data = [{"index": i, "embedding": [float(i)]} for i in reversed(range(len(json["input"])))]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    e = OpenAIEmbedder("sk-x", model="text-embedding-3-small", dim=384, batch_size=2)
    out = e.embed_documents(["a", "b", "c"])
    assert out == [[0.0], [1.0], [0.0]]  # batches of 2 then 1, each ordered by index
    assert len(calls) == 2
    assert calls[0][0].endswith("/embeddings")
    assert calls[0][1]["Authorization"] == "Bearer sk-x"
    assert calls[0][2]["dimensions"] == 384


def test_openai_embedder_http_error(monkeypatch):
    def boom(url, headers, json, timeout):
        return httpx.Response(500, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(EmbeddingError):
        OpenAIEmbedder("k").embed_query("x")


@pytest.mark.slow
def test_real_sentence_transformer_semantic_similarity():
    e = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    assert e.dim == 384
    q = e.embed_query("How many vacation days do I get?")
    near = e.embed_query("Employees accrue 20 days of paid time off per year.")
    far = e.embed_query("The database connection pool is exhausted.")
    assert cos(q, near) > cos(q, far)
