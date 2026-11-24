from __future__ import annotations

from tests.helpers import make_docx, make_pdf

MD = b"# Leave\n\n## PTO\nFull-time employees receive 20 days of PTO every year.\n"


def upload(client, *files):
    return client.post("/upload", files=[("files", f) for f in files])


def test_upload_single_markdown(api_env):
    client, container, _ = api_env
    r = upload(client, ("handbook.md", MD, "text/markdown"))
    assert r.status_code == 200
    body = r.json()
    assert body["indexed"] == 1 and body["failed"] == 0
    item = body["results"][0]
    assert item["status"] == "indexed" and item["filename"] == "handbook.md" and item["chunk_count"] >= 1
    assert container.vector_store.count(item["doc_id"]) == item["chunk_count"]


def test_upload_multiple_formats_in_one_request(api_env):
    client, _, _ = api_env
    r = upload(
        client,
        ("a.md", MD, "text/markdown"),
        ("b.txt", b"Plain text about security.", "text/plain"),
        ("c.docx", make_docx([("Sec", ["Use MFA."])]), "application/octet-stream"),
        ("d.pdf", make_pdf(["Page one", "Page two"]), "application/pdf"),
    )
    assert r.status_code == 200 and r.json()["indexed"] == 4
    docs = client.get("/documents").json()
    assert docs["total"] == 4 and {d["file_type"] for d in docs["documents"]} == {"md", "txt", "docx", "pdf"}
    assert [d["page_count"] for d in docs["documents"] if d["file_type"] == "pdf"] == [2]


def test_duplicate_and_replace(api_env):
    client, _, _ = api_env
    first = upload(client, ("p.md", MD, "text/markdown")).json()["results"][0]
    dup = upload(client, ("copy.md", MD, "text/markdown")).json()["results"][0]
    assert dup["status"] == "duplicate" and dup["doc_id"] == first["doc_id"]
    rep = upload(client, ("p.md", b"# New\nBrand new content here.\n", "text/markdown")).json()["results"][0]
    assert rep["status"] == "replaced" and rep["replaced_doc_id"] == first["doc_id"]
    assert client.get("/documents").json()["total"] == 1


def test_unsupported_type_is_415(api_env):
    client, container, _ = api_env
    r = upload(client, ("virus.exe", b"MZ...", "application/octet-stream"))
    assert r.status_code == 415
    item = r.json()["results"][0]
    assert item["status"] == "failed" and item["error_type"] == "UnsupportedFileTypeError" and ".exe" in item["error"]
    assert container.ingestion.list_documents() == []


def test_too_large_is_413(api_env):
    client, container, _ = api_env
    container.settings.max_upload_mb = 1
    r = upload(client, ("big.txt", b"a" * (1024 * 1024 + 1), "text/plain"))
    assert r.status_code == 413 and r.json()["results"][0]["error_type"] == "FileTooLargeError"
    assert container.ingestion.list_documents() == []


def test_exactly_at_limit_is_accepted(api_env):
    client, container, _ = api_env
    container.settings.max_upload_mb = 1
    assert upload(client, ("ok.txt", b"word " * ((1024 * 1024) // 5), "text/plain")).status_code == 200


def test_empty_and_corrupt_files_are_422(api_env):
    client, _, _ = api_env
    r = upload(client, ("empty.txt", b"", "text/plain"))
    assert r.status_code == 422 and r.json()["results"][0]["error_type"] == "EmptyDocumentError"
    r = upload(client, ("bad.pdf", b"definitely not a pdf", "application/pdf"))
    assert r.status_code == 422 and r.json()["results"][0]["error_type"] == "CorruptDocumentError"
    r = upload(client, ("bad.docx", b"nope", "application/octet-stream"))
    assert r.status_code == 422


def test_partial_success_returns_200_with_per_file_results(api_env):
    client, _, _ = api_env
    r = upload(client, ("good.md", MD, "text/markdown"), ("bad.xyz", b"data", "text/plain"), ("empty.md", b"", "text/plain"))
    assert r.status_code == 200
    body = r.json()
    assert body["indexed"] == 1 and body["failed"] == 2
    assert [x["status"] for x in body["results"]] == ["indexed", "failed", "failed"]


def test_upload_without_files_is_422(api_env):
    client, _, _ = api_env
    assert client.post("/upload").status_code == 422


def test_upload_filename_path_is_sanitised(api_env):
    client, _, _ = api_env
    r = upload(client, ("../../etc/passwd.txt", b"hello world", "text/plain"))
    assert r.status_code == 200 and r.json()["results"][0]["filename"] == "passwd.txt"


def test_list_get_and_delete_documents(api_env):
    client, container, _ = api_env
    assert client.get("/documents").json() == {"documents": [], "total": 0, "total_chunks": 0}
    a = upload(client, ("a.md", MD, "text/markdown")).json()["results"][0]
    b = upload(client, ("b.txt", b"Another document body.", "text/plain")).json()["results"][0]

    listing = client.get("/documents").json()
    assert listing["total"] == 2 and listing["total_chunks"] == a["chunk_count"] + b["chunk_count"]
    one = client.get(f"/documents/{a['doc_id']}")
    assert one.status_code == 200 and one.json()["filename"] == "a.md" and one.json()["size_bytes"] == len(MD)

    d = client.delete(f"/documents/{a['doc_id']}")
    assert d.status_code == 200 and d.json() == {"deleted": a["doc_id"]}
    assert container.vector_store.count(a["doc_id"]) == 0
    assert [x["doc_id"] for x in client.get("/documents").json()["documents"]] == [b["doc_id"]]
    assert client.get(f"/documents/{a['doc_id']}").status_code == 404


def test_delete_and_get_unknown_are_404(api_env):
    client, _, _ = api_env
    assert client.delete("/documents/nope").status_code == 404
    assert client.get("/documents/nope").status_code == 404


def test_health_reports_document_count(api_env):
    client, _, _ = api_env
    assert client.get("/health").json()["documents"] == 0
    upload(client, ("a.md", MD, "text/markdown"))
    assert client.get("/health").json()["documents"] == 1


def test_service_unavailable_without_container(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app(settings))  # no lifespan context -> container never built
    assert client.get("/documents").status_code == 503
