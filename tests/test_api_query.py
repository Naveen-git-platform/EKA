from __future__ import annotations

import json

import pytest

from app.api.routes.query import NO_DOCUMENTS_TEXT
from app.api.sse import format_sse
from app.core.llm import LLMError

PTO_DOC = b"# Leave\n\n## PTO\nFull-time employees receive 20 days of PTO every year.\n"
MEALS_DOC = b"# Expenses\nMeals are reimbursed up to $75 per day while traveling.\n"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into [(event, data), ...], asserting the frame format is strictly valid."""
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n")
        assert len(lines) == 2, f"each frame must be exactly event+data lines, got {lines!r}"
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ")
        data = json.loads(lines[1][len("data: "):])
        assert data["type"] == lines[0][len("event: "):]
        frames.append((lines[0][len("event: "):], data))
    return frames


def ask(client, question="How many PTO days do I get?", **extra):
    return client.post("/query", json={"question": question, **extra})


@pytest.fixture
def loaded(api_env):
    client, container, llm = api_env
    container.ingestion.ingest_bytes("handbook.md", PTO_DOC)
    container.ingestion.ingest_bytes("expenses.md", MEALS_DOC)
    return client, container, llm


# ------------------------------------------------------------------ SSE streaming
def test_query_streams_server_sent_events(loaded):
    client, _, _ = loaded
    r = ask(client)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "no-cache" in r.headers["cache-control"] and r.headers["x-accel-buffering"] == "no"

    frames = parse_sse(r.text)
    names = [n for n, _ in frames]
    collapsed = [n for i, n in enumerate(names) if i == 0 or n != names[i - 1]]
    assert collapsed == ["plan", "retrieval", "critique", "token", "citations", "done"]

    streamed = "".join(d["text"] for n, d in frames if n == "token")
    done = frames[-1][1]
    assert streamed.strip() == done["answer"] == "Full-time employees receive 20 days of PTO [1]."
    assert done["ok"] is True and done["grounded"] is True
    cites = next(d for n, d in frames if n == "citations")["citations"]
    assert cites[0]["filename"] == "handbook.md" and "20 days" in cites[0]["text"]


def test_query_events_arrive_as_many_token_frames(loaded):
    client, _, llm = loaded
    llm.scripts["answer"] = "one two three four five six [1]"
    frames = parse_sse(ask(client).text)
    assert sum(1 for n, _ in frames if n == "token") >= 6


def test_sse_frame_survives_newlines_and_unicode_in_text():
    frame = format_sse({"type": "token", "text": "line1\nline2 — “quoted” 日本語"})
    assert frame.count("\n") == 3 and frame.endswith("\n\n")  # embedded newline is JSON-escaped, not raw
    assert parse_sse(frame)[0][1]["text"] == "line1\nline2 — “quoted” 日本語"


def test_non_streaming_mode_returns_json(loaded):
    client, _, _ = loaded
    r = ask(client, stream=False)
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    body = r.json()
    assert body["answer"].startswith("Full-time employees") and body["ok"] and body["grounded"]
    assert body["question"] == "How many PTO days do I get?" and body["iterations"] == 1
    assert body["citations"][0]["filename"] == "handbook.md" and body["plan"]["strategy"] == "direct"
    assert [t["node"] for t in body["trace"]] == ["planner", "retriever", "critic", "answer"]


# ------------------------------------------------------------------ request handling
def test_empty_knowledge_base_gets_friendly_message_without_llm(api_env):
    client, _, llm = api_env
    frames = parse_sse(ask(client).text)
    assert [n for n, _ in frames] == ["token", "citations", "done"]
    assert frames[0][1]["text"] == NO_DOCUMENTS_TEXT and frames[-1][1]["grounded"] is False
    assert llm.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 2001},
        {"question": "ok", "top_k": 0},
        {"question": "ok", "top_k": 21},
        {"question": "ok", "history": [{"role": "system", "content": "x"}]},
        {"question": "ok", "history": [{"role": "user", "content": ""}]},
        {"question": "ok", "history": [{"role": "user", "content": "x"}] * 41},
        {"question": "ok", "doc_ids": "not-a-list"},
    ],
)
def test_invalid_requests_are_422(loaded, payload):
    client, _, llm = loaded
    r = client.post("/query", json=payload)
    assert r.status_code == 422 and llm.calls == []


def test_invalid_json_body_is_422(loaded):
    client, _, _ = loaded
    assert client.post("/query", content=b"{oops", headers={"content-type": "application/json"}).status_code == 422


def test_question_is_trimmed(loaded):
    client, _, llm = loaded
    ask(client, "   spaced out question   ")
    assert "QUESTION: spaced out question\n" in llm.calls_for("planner")[0]["messages"][-1]["content"] + "\n"


def test_doc_ids_restrict_retrieval(loaded):
    client, container, _ = loaded
    meals = next(d for d in container.ingestion.list_documents() if d.filename == "expenses.md")
    frames = parse_sse(ask(client, doc_ids=[meals.doc_id]).text)
    files = {c["filename"] for c in next(d for n, d in frames if n == "retrieval")["chunks"]}
    assert files == {"expenses.md"}


def test_history_is_forwarded_to_agents(loaded):
    client, _, llm = loaded
    history = [{"role": "user", "content": "What leave exists?"}, {"role": "assistant", "content": "PTO and parental."}]
    ask(client, "and how many days is it?", history=history)
    assert "What leave exists?" in llm.calls_for("planner")[0]["messages"][-1]["content"]


def test_top_k_is_forwarded(loaded):
    client, _, _ = loaded
    frames = parse_sse(ask(client, top_k=1).text)
    assert len(next(d for n, d in frames if n == "retrieval")["chunks"]) <= 2


# ------------------------------------------------------------------ failure handling in-band
def test_llm_failure_is_reported_as_error_event_then_done(loaded):
    client, _, llm = loaded
    llm.scripts["answer"] = LLMError("429 quota exceeded")
    r = ask(client)
    assert r.status_code == 200  # headers were already sent: errors travel in-band
    frames = parse_sse(r.text)
    assert frames[-1][0] == "done" and frames[-1][1]["ok"] is False
    err = next(d for n, d in frames if n == "error")
    assert err["stage"] == "answer" and "quota" in err["message"]


def test_unexpected_server_error_is_reported_in_band(loaded, monkeypatch):
    client, container, _ = loaded

    async def broken(*a, **k):
        raise RuntimeError("kaboom")
        yield  # pragma: no cover

    monkeypatch.setattr(container.agent, "stream", broken)
    frames = parse_sse(ask(client).text)
    assert [n for n, _ in frames] == ["error", "done"]
    assert frames[0][1]["stage"] == "server" and "kaboom" in frames[0][1]["message"] and frames[1][1]["ok"] is False


def test_non_streaming_mode_failure_still_returns_json(loaded):
    client, _, llm = loaded
    llm.scripts["answer"] = LLMError("down")
    r = ask(client, stream=False)
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["errors"]


def test_cors_headers_present(loaded):
    client, _, _ = loaded
    r = client.options("/query", headers={"Origin": "http://localhost:8501", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] in ("*", "http://localhost:8501")


def test_openapi_lists_all_phase5_endpoints(api_env):
    client, _, _ = api_env
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/upload", "/query", "/documents", "/documents/{doc_id}", "/health"} <= set(paths)
