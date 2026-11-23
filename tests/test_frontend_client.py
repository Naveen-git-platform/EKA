from __future__ import annotations

import json

import httpx
import pytest

from frontend.client import APIError, EKAClient, iter_sse


def frame(event: str, **data) -> list[str]:
    return [f"event: {event}\n", f"data: {json.dumps({'type': event, **data})}\n", "\n"]


# ------------------------------------------------------------------ SSE parser
def test_iter_sse_basic_frames():
    lines = [*frame("plan", strategy="direct"), *frame("token", text="Hi"), *frame("done", ok=True)]
    assert [(e, d["type"]) for e, d in iter_sse(lines)] == [("plan", "plan"), ("token", "token"), ("done", "done")]


def test_iter_sse_ignores_comments_blank_noise_and_crlf():
    lines = [": keep-alive\r\n", "\r\n", "event: token\r\n", 'data: {"type": "token", "text": "x"}\r\n', "\r\n", "\n"]
    assert list(iter_sse(lines)) == [("token", {"type": "token", "text": "x"})]


def test_iter_sse_skips_bad_json_and_non_objects_but_continues():
    lines = ["event: a\n", "data: {not json\n", "\n", "event: b\n", "data: [1, 2]\n", "\n", *frame("ok", n=1)]
    assert [e for e, _ in iter_sse(lines)] == ["ok"]


def test_iter_sse_multiline_data_and_missing_event_name():
    lines = ["data: {\n", 'data: "type": "token",\n', 'data: "text": "multi"\n', "data: }\n", "\n"]
    assert list(iter_sse(lines)) == [("token", {"type": "token", "text": "multi"})]


def test_iter_sse_flushes_final_frame_without_trailing_blank_line():
    lines = ["event: done\n", 'data: {"type": "done"}\n']
    assert list(iter_sse(lines)) == [("done", {"type": "done"})]


def test_iter_sse_is_lazy():
    pulled = []

    def gen():
        for ln in [*frame("a"), *frame("b")]:
            pulled.append(ln)
            yield ln

    it = iter_sse(gen())
    assert next(it)[0] == "a" and len(pulled) == 3  # first frame yielded before the rest is consumed


def test_iter_sse_roundtrips_backend_format():
    from app.api.sse import format_sse

    ev = {"type": "token", "text": "line1\nline2 — ünï"}
    assert list(iter_sse(format_sse(ev).splitlines(keepends=True))) == [("token", ev)]


# ------------------------------------------------------------------ client
def client_with(handler) -> EKAClient:
    return EKAClient("http://backend:8000", transport=httpx.MockTransport(handler))


def test_simple_requests_and_paths():
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path, dict(req.url.params)))
        return httpx.Response(200, json={"ok": True})

    c = client_with(handler)
    c.health(); c.list_documents(); c.load_samples(); c.delete_document("abc"); c.list_runs(5)  # noqa: E702
    c.list_evaluations(10, run_id="r1"); c.get_run("r1"); c.evaluate("q?", "gt")  # noqa: E702
    assert seen == [
        ("GET", "/health", {}), ("GET", "/documents", {}), ("POST", "/samples/load", {}),
        ("DELETE", "/documents/abc", {}), ("GET", "/evaluations/runs", {"limit": "5"}),
        ("GET", "/evaluations", {"limit": "10", "run_id": "r1"}), ("GET", "/evaluations/runs/r1", {}),
        ("POST", "/evaluate", {}),
    ]


def test_upload_sends_multipart_files():
    captured = {}

    def handler(req: httpx.Request):
        captured["ct"], captured["body"] = req.headers["content-type"], req.content
        return httpx.Response(200, json={"results": [], "indexed": 2, "failed": 0})

    out = client_with(handler).upload([("a.md", b"# A"), ("b.txt", b"bee")])
    assert out["indexed"] == 2 and captured["ct"].startswith("multipart/form-data")
    assert b'filename="a.md"' in captured["body"] and b'filename="b.txt"' in captured["body"] and b"bee" in captured["body"]


def test_http_errors_become_api_errors_with_useful_messages():
    def handler(req: httpx.Request):
        if req.url.path == "/documents/nope":
            return httpx.Response(404, json={"detail": "Document 'nope' not found"})
        if req.url.path == "/upload":
            return httpx.Response(415, json={"results": [{"filename": "x.exe", "status": "failed", "error": "Unsupported file type"}]})
        if req.url.path == "/query":
            return httpx.Response(422, json={"detail": [{"loc": ["body", "question"], "msg": "String should have at least 1 character"}]})
        return httpx.Response(500, text="boom")

    c = client_with(handler)
    with pytest.raises(APIError, match="not found") as e:
        c.delete_document("nope")
    assert e.value.status == 404
    with pytest.raises(APIError, match=r"x\.exe: Unsupported file type"):
        c.upload([("x.exe", b"1")])
    with pytest.raises(APIError, match="question: String should"):
        list(c.stream_query(""))
    with pytest.raises(APIError, match="boom"):
        c.health()


def test_connection_failure_is_api_error():
    def handler(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(APIError, match="Cannot reach the backend"):
        client_with(handler).health()
    with pytest.raises(APIError, match="lost"):
        list(client_with(handler).stream_query("q"))


def test_stream_query_yields_events_and_sends_options():
    seen = {}
    body = "".join(frame("plan", strategy="direct") + frame("token", text="Hello") + frame("done", ok=True, answer="Hello"))

    def handler(req: httpx.Request):
        seen["json"] = json.loads(req.content)
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    events = list(client_with(handler).stream_query("Q?", history=[{"role": "user", "content": "hi"}], doc_ids=["d1"],
                                                     top_k=3, evaluate=True))
    assert [e["type"] for e in events] == ["plan", "token", "done"]
    assert seen["json"] == {"question": "Q?", "history": [{"role": "user", "content": "hi"}], "evaluate": True,
                            "stream": True, "doc_ids": ["d1"], "top_k": 3}


def test_start_batch_payload():
    seen = {}

    def handler(req):
        seen["json"] = json.loads(req.content)
        return httpx.Response(202, json={"run_id": "r"})

    assert client_with(handler).start_batch(limit=5, name="n")["run_id"] == "r"
    assert seen["json"] == {"use_sample": True, "limit": 5, "name": "n"}


def test_client_against_the_real_backend_app(api_env):
    """End-to-end: EKAClient <-> real FastAPI app (in-process ASGI), including incremental SSE parsing."""

    test_client, container, _ = api_env
    container.ingestion.ingest_bytes("handbook.md", b"# Leave\n\n## PTO\nFull-time employees receive 20 days of PTO.\n")

    class Bridge(httpx.BaseTransport):  # route EKAClient's requests into the TestClient (itself an httpx client)
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            r = test_client.request(request.method, str(request.url.path), content=request.content,
                                    headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
                                    params=dict(request.url.params))
            return httpx.Response(r.status_code, headers=r.headers, content=r.content)

    c = EKAClient("http://testserver", transport=Bridge())
    assert c.health()["documents"] == 1 and c.list_documents()["total"] == 1
    events = list(c.stream_query("How many PTO days?"))
    assert [e["type"] for e in events][0] == "plan" and events[-1]["type"] == "done" and events[-1]["ok"]
    assert "".join(e["text"] for e in events if e["type"] == "token").strip().startswith("Full-time")
