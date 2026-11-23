from __future__ import annotations

import pytest

from app.core.embeddings import EmbeddingError
from app.core.vectorstore import VectorStoreError
from app.ingestion.errors import (
    CorruptDocumentError,
    DocumentNotFoundError,
    EmptyDocumentError,
    FileTooLargeError,
    IngestionError,
    UnsupportedFileTypeError,
)
from app.ingestion.indexer import IngestionService
from tests.helpers import make_docx, make_pdf

MD = (
    b"# Leave\n\n## PTO\nFull-time employees accrue 20 days of paid time off per year. "
    b"Unused days carry over up to 5 days.\n\n## Parental\nPrimary caregivers get 16 weeks of paid leave.\n"
)


def assert_empty(svc: IngestionService):
    assert svc.list_documents() == []
    assert svc.vector_store.count() == 0
    assert list(svc.chunk_store.iter_chunks()) == []
    assert len(svc.bm25) == 0


def test_ingest_markdown_end_to_end(ingestion):
    res = ingestion.ingest_bytes("handbook.md", MD)
    assert res.status == "indexed" and res.chunk_count >= 2 and len(res.doc_id) == 16
    docs = ingestion.list_documents()
    assert [d.filename for d in docs] == ["handbook.md"]
    assert docs[0].chunk_count == res.chunk_count and docs[0].file_type == "md"
    assert ingestion.vector_store.count(res.doc_id) == res.chunk_count
    assert len(list(ingestion.chunk_store.iter_chunks())) == res.chunk_count
    assert len(ingestion.bm25) == res.chunk_count
    assert ingestion.get_document(res.doc_id).sha256.startswith(res.doc_id)


def test_each_format_ingests(ingestion):
    r1 = ingestion.ingest_bytes("a.txt", b"Plain text document about passwords.")
    r2 = ingestion.ingest_bytes("b.docx", make_docx([("Security", ["Use MFA."])]))
    r3 = ingestion.ingest_bytes("c.pdf", make_pdf(["Page one text", "Page two text"]))
    r4 = ingestion.ingest_bytes("d.md", MD)
    assert {r.status for r in (r1, r2, r3, r4)} == {"indexed"}
    assert r3.page_count == 2
    assert {d.file_type for d in ingestion.list_documents()} == {"txt", "docx", "pdf", "md"}


def test_pdf_chunks_carry_page_metadata(ingestion):
    ingestion.ingest_bytes("c.pdf", make_pdf(["Alpha content here", "Beta content here"]))
    chunks = list(ingestion.chunk_store.iter_chunks())
    assert sorted(c.page for c in chunks) == [1, 2]


def test_duplicate_content_is_skipped(ingestion):
    first = ingestion.ingest_bytes("handbook.md", MD)
    second = ingestion.ingest_bytes("copy-of-handbook.md", MD)
    assert second.status == "duplicate" and second.doc_id == first.doc_id
    assert len(ingestion.list_documents()) == 1
    assert ingestion.vector_store.count() == first.chunk_count  # no duplicate vectors
    assert len(ingestion.bm25) == first.chunk_count


def test_same_filename_new_content_replaces_old(ingestion):
    old = ingestion.ingest_bytes("policy.md", MD)
    new = ingestion.ingest_bytes("policy.md", b"# Policy\nCompletely new text about security.\n")
    assert new.status == "replaced" and new.replaced_doc_id == old.doc_id
    assert [d.doc_id for d in ingestion.list_documents()] == [new.doc_id]
    assert ingestion.vector_store.count(old.doc_id) == 0
    assert ingestion.vector_store.count() == new.chunk_count
    assert ingestion.chunk_store.load(old.doc_id) == []
    assert all("20 days" not in c.text for c in ingestion.chunk_store.iter_chunks())
    assert len(ingestion.bm25) == new.chunk_count


def test_delete_removes_everything(ingestion):
    a = ingestion.ingest_bytes("a.md", MD)
    b = ingestion.ingest_bytes("b.txt", b"Other document text here.")
    ingestion.delete_document(a.doc_id)
    assert [d.doc_id for d in ingestion.list_documents()] == [b.doc_id]
    assert ingestion.vector_store.count(a.doc_id) == 0
    assert ingestion.vector_store.count() == b.chunk_count
    assert len(ingestion.bm25) == b.chunk_count
    assert ingestion.bm25.search("paid time off", 5) == []
    ingestion.delete_document(b.doc_id)
    assert_empty(ingestion)


def test_delete_unknown_raises(ingestion):
    with pytest.raises(DocumentNotFoundError):
        ingestion.delete_document("nope")
    with pytest.raises(DocumentNotFoundError):
        ingestion.get_document("nope")


@pytest.mark.parametrize(
    "filename,data,exc",
    [
        ("notes.xlsx", b"x", UnsupportedFileTypeError),
        ("README", b"x", UnsupportedFileTypeError),
        ("empty.txt", b"", EmptyDocumentError),
        ("blank.md", b"  \n ", EmptyDocumentError),
        ("bad.pdf", b"not a pdf at all", CorruptDocumentError),
        ("bad.docx", b"not a docx", CorruptDocumentError),
    ],
)
def test_bad_inputs_raise_and_persist_nothing(ingestion, filename, data, exc):
    with pytest.raises(exc):
        ingestion.ingest_bytes(filename, data)
    assert_empty(ingestion)


def test_oversize_rejected(settings, embedder, vector_store):
    settings.max_upload_mb = 1
    svc = IngestionService.from_settings(settings, embedder, vector_store)
    with pytest.raises(FileTooLargeError):
        svc.ingest_bytes("big.txt", b"a" * (1024 * 1024 + 1))
    assert_empty(svc)


def test_embedding_failure_persists_nothing(ingestion):
    class Boom:
        dim = 256

        def embed_documents(self, texts):
            raise EmbeddingError("model offline")

        def embed_query(self, text):
            raise EmbeddingError("model offline")

    ingestion.embedder = Boom()
    with pytest.raises(IngestionError, match="Embedding failed"):
        ingestion.ingest_bytes("a.md", MD)
    assert_empty(ingestion)


def test_vector_store_failure_rolls_back(ingestion, monkeypatch):
    def boom(*a, **k):
        raise VectorStoreError("qdrant down")

    monkeypatch.setattr(ingestion.vector_store, "upsert", boom)
    with pytest.raises(VectorStoreError):
        ingestion.ingest_bytes("a.md", MD)
    assert_empty(ingestion)


def test_registry_failure_rolls_back_vectors_and_chunks(ingestion, monkeypatch):
    def boom(rec):
        raise RuntimeError("disk full")

    monkeypatch.setattr(ingestion.registry, "add", boom)
    with pytest.raises(IngestionError, match="Failed to index"):
        ingestion.ingest_bytes("a.md", MD)
    assert ingestion.vector_store.count() == 0
    assert list(ingestion.chunk_store.iter_chunks()) == []


def test_failed_replace_keeps_old_version(ingestion, monkeypatch):
    old = ingestion.ingest_bytes("policy.md", MD)
    monkeypatch.setattr(ingestion.vector_store, "upsert", lambda *a, **k: (_ for _ in ()).throw(VectorStoreError("x")))
    with pytest.raises(VectorStoreError):
        ingestion.ingest_bytes("policy.md", b"# New\nSomething different entirely.\n")
    assert [d.doc_id for d in ingestion.list_documents()] == [old.doc_id]
    assert ingestion.vector_store.count(old.doc_id) == old.chunk_count


def test_filename_path_is_sanitised(ingestion):
    res = ingestion.ingest_bytes("../../etc/evil.txt", b"harmless content")
    assert res.filename == "evil.txt"


def test_unicode_filename(ingestion):
    res = ingestion.ingest_bytes("政策.md", "# 政策\n内容 content here.\n".encode())
    assert res.filename == "政策.md"


def test_progress_callback_stages(ingestion):
    stages = []
    ingestion.ingest_bytes("a.md", MD, on_progress=lambda s, info: stages.append(s))
    assert stages[0] == "parsing" and stages[-1] == "done"
    assert {"chunking", "embedding", "indexing"} <= set(stages)


def test_bm25_and_state_rebuilt_on_restart(settings, embedder, vector_store, ingestion):
    res = ingestion.ingest_bytes("a.md", MD)
    restarted = IngestionService.from_settings(settings, embedder, vector_store)  # same dirs, fresh process
    assert len(restarted.bm25) == res.chunk_count
    assert [d.doc_id for d in restarted.list_documents()] == [res.doc_id]
    assert restarted.bm25.search("parental caregivers", 1)


def test_ingest_path(ingestion, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("A note about vacation policy.", encoding="utf-8")
    assert ingestion.ingest_path(p).status == "indexed"
    with pytest.raises(IngestionError):
        ingestion.ingest_path(tmp_path / "missing.txt")
