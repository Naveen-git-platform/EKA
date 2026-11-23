"""Drives the real Streamlit script with AppTest against a scripted fake backend client."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from frontend import client as client_mod

APP = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")

DOCS = [
    {"doc_id": "d1", "filename": "handbook.md", "file_type": "md", "size_bytes": 10, "chunk_count": 7,
     "page_count": None, "created_at": "2026-01-01T00:00:00+00:00"},
    {"doc_id": "d2", "filename": "faq.txt", "file_type": "txt", "size_bytes": 10, "chunk_count": 3,
     "page_count": None, "created_at": "2026-01-01T00:00:00+00:00"},
]
SOURCE = {"index": 1, "chunk_id": "c1", "doc_id": "d1", "filename": "handbook.md", "page": None, "section": "Leave > PTO",
          "score": 0.91, "snippet": "Full-time employees accrue 20 days of paid time off.",
          "text": "Full-time employees accrue 20 days of paid time off (PTO) per year. Part-time staff accrue pro rata."}
ANSWER = "Full-time employees receive 20 days of PTO [1]."


def good_events(answer=ANSWER):
    yield {"type": "plan", "strategy": "direct", "standalone_query": "q", "sub_queries": ["PTO days"],
           "reasoning": "", "fallback": False}
    yield {"type": "retrieval", "iteration": 1, "queries": ["PTO days"], "total": 1, "chunks": [
        {"chunk_id": "c1", "filename": "handbook.md", "page": None, "section": None, "score": 0.9,
         "sources": ["vector"], "snippet": "x"}]}
    yield {"type": "critique", "iteration": 1, "sufficient": True, "confidence": 0.9, "relevance": 0.9,
           "coverage": 0.9, "missing_information": "", "rewritten_queries": [], "will_retry": False,
           "reasoning": "", "degraded": False}
    for tok in answer.split(" "):
        yield {"type": "token", "text": tok + " "}
    other = {**SOURCE, "index": 2, "chunk_id": "c2", "text": "other", "snippet": "other"}
    yield {"type": "citations", "citations": [SOURCE], "sources": [SOURCE, other]}
    yield {"type": "done", "ok": True, "answer": answer, "iterations": 1, "elapsed_ms": 123.0, "trace": [],
           "errors": [], "grounded": True}


EVAL_RESULT = {
    "id": "e1", "run_id": None, "created_at": "2026-01-01T10:00:00+00:00", "source": "auto", "backend": "custom",
    "question": "How many PTO days?", "ground_truth": None, "answer": ANSWER, "contexts": [SOURCE["text"]],
    "faithfulness": 1.0, "answer_relevancy": 0.82, "context_precision": 0.6, "context_recall": None, "overall": 0.81,
    "unsupported_claims": ["a claim"], "errors": [], "latency_ms": 1.0, "case_id": None, "category": "standard",
}


class FakeClient:
    def __init__(self, *, provider="groq", configured=True, docs=None, events=None, health_error=None, evals=None):
        self.provider, self.configured = provider, configured
        self.docs = list(DOCS if docs is None else docs)
        self.events = events or (lambda **kw: good_events())
        self.health_error = health_error
        self.eval_results = list(evals or [])
        self.stream_calls, self.deleted, self.batches, self.uploads = [], [], [], []
        self.evals_listed = 0

    def health(self):
        if self.health_error:
            raise client_mod.APIError(self.health_error)
        return {"status": "ok", "llm_provider": self.provider, "llm_model": "m", "llm_configured": self.configured,
                "embedding_provider": "sentence-transformers", "documents": len(self.docs)}

    def list_documents(self):
        return {"documents": self.docs, "total": len(self.docs), "total_chunks": 10}

    def delete_document(self, doc_id):
        self.deleted.append(doc_id)
        self.docs = [d for d in self.docs if d["doc_id"] != doc_id]

    def upload(self, files):
        self.uploads.append(files)
        results = [{"filename": n, "status": "indexed", "chunk_count": 2} for n, _ in files]
        return {"results": results, "indexed": len(files), "failed": 0}

    def load_samples(self):
        return {"results": [], "indexed": 4, "failed": 0}

    def stream_query(self, question, **kw):
        self.stream_calls.append({"question": question, **kw})
        yield from self.events(question=question, **kw)

    def list_evaluations(self, limit=50, run_id=None):
        self.evals_listed += 1
        results = self.eval_results
        if self.evals_listed >= 2 and not results and self.stream_calls:  # auto-evaluation "completes" after the answer
            results = [EVAL_RESULT]
        agg = {"faithfulness": 1.0, "answer_relevancy": 0.82, "context_precision": 0.6, "context_recall": None,
               "overall": 0.81, "count": float(len(results))}
        return {"results": results, "total": len(results), "aggregate": agg}

    def list_runs(self, limit=20):
        return {"runs": [{"run_id": "r1", "name": "sample set", "status": "completed", "total": 3, "completed": 3,
                          "created_at": "x", "backend": "custom", "aggregate": {}}]}

    def get_run(self, run_id):
        return {"run_id": run_id, "name": "n", "status": "completed", "total": 3, "completed": 3, "created_at": "x",
                "backend": "custom", "aggregate": {}}

    def start_batch(self, *, limit=None, name=None):
        self.batches.append((limit, name))
        return {"run_id": "r2", "status": "running", "total": limit or 0, "completed": 0}


def make_app(monkeypatch, **kw) -> tuple[AppTest, FakeClient]:
    fake = FakeClient(**kw)
    monkeypatch.setattr(client_mod, "EKAClient", lambda url: fake)
    return AppTest.from_file(APP, default_timeout=20), fake


def texts(elements) -> str:
    return "\n".join(str(getattr(e, "value", "")) for e in elements)


# ------------------------------------------------------------------ rendering
def test_initial_render_shows_documents_and_empty_chat(monkeypatch):
    at, _ = make_app(monkeypatch)
    at.run()
    assert not at.exception
    assert "Ask your documents" in texts(at.markdown)
    assert "handbook.md" in texts(at.sidebar.markdown) and "faq.txt" in texts(at.sidebar.markdown)
    assert len(at.chat_message) == 0 and len(at.chat_input) == 1


def test_backend_down_shows_error_and_stops(monkeypatch):
    at, _ = make_app(monkeypatch, health_error="Cannot reach the backend at http://x")
    at.run()
    assert not at.exception
    assert any("Cannot reach the backend" in e.value for e in at.sidebar.error)
    assert len(at.chat_input) == 0


def test_offline_mode_and_missing_key_notices(monkeypatch):
    at, _ = make_app(monkeypatch, provider="fake")
    at.run()
    assert any("Offline demo mode" in i.value for i in at.sidebar.info)
    at2, _ = make_app(monkeypatch, provider="groq", configured=False)
    at2.run()
    assert any("No API key" in w.value for w in at2.sidebar.warning)


def test_empty_knowledge_base_hint(monkeypatch):
    at, _ = make_app(monkeypatch, docs=[])
    at.run()
    assert any("No documents yet" in c.value for c in at.sidebar.caption)


# ------------------------------------------------------------------ chat
def test_chat_turn_streams_answer_with_sources_and_trace(monkeypatch):
    at, fake = make_app(monkeypatch)
    at.run()
    at.chat_input[0].set_value("How many PTO days?").run()
    assert not at.exception
    assert [m.name for m in at.chat_message] == ["user", "assistant"]
    assert "20 days of PTO" in texts(at.chat_message[1].markdown)
    labels = [e.label for e in at.expander]
    assert any("[1] handbook.md" in lab for lab in labels)
    assert any("How the agents answered" in lab for lab in labels)
    assert any("Also retrieved" in lab for lab in labels)
    call = fake.stream_calls[0]
    assert call["question"] == "How many PTO days?" and call["history"] == [] and call["top_k"] == 5
    assert call["evaluate"] is False and not call["doc_ids"]
    # the cited sentence is highlighted in the source card
    all_md = "".join(texts(e.markdown) for e in at.expander)
    assert "<mark>Full-time employees accrue 20 days" in all_md


def test_follow_up_sends_conversation_history(monkeypatch):
    at, fake = make_app(monkeypatch)
    at.run()
    at.chat_input[0].set_value("How many PTO days?").run()
    at.chat_input[0].set_value("And for part-time?").run()
    assert not at.exception
    second = fake.stream_calls[1]
    assert second["history"] == [{"role": "user", "content": "How many PTO days?"},
                                 {"role": "assistant", "content": ANSWER}]
    assert [m.name for m in at.chat_message] == ["user", "assistant", "user", "assistant"]


def test_clear_conversation(monkeypatch):
    at, _ = make_app(monkeypatch)
    at.run()
    at.chat_input[0].set_value("hello?").run()
    next(b for b in at.sidebar.button if b.label == "Clear conversation").click().run()
    assert len(at.chat_message) == 0


def test_error_events_are_shown_not_crashing(monkeypatch):
    def events(**kw):
        yield {"type": "plan", "strategy": "direct", "standalone_query": "q", "sub_queries": ["q"],
               "reasoning": "", "fallback": True}
        yield {"type": "error", "stage": "answer", "message": "429 quota exceeded"}
        yield {"type": "done", "ok": False, "answer": "", "iterations": 1, "elapsed_ms": 5.0, "trace": [],
               "errors": ["answer: 429 quota exceeded"], "grounded": False}

    at, _ = make_app(monkeypatch, events=events)
    at.run()
    at.chat_input[0].set_value("anything?").run()
    assert not at.exception
    assert any("quota" in w.value for w in at.warning)
    assert "No answer was produced" in texts(at.chat_message[1].markdown)


def test_connection_loss_mid_stream_is_reported(monkeypatch):
    def events(**kw):
        yield {"type": "token", "text": "partial "}
        raise client_mod.APIError("Connection to the backend was lost")

    at, _ = make_app(monkeypatch, events=events)
    at.run()
    at.chat_input[0].set_value("q?").run()
    assert not at.exception and any("lost" in w.value for w in at.warning)
    assert "partial" in texts(at.chat_message[1].markdown)


def test_document_filter_and_top_k_are_forwarded(monkeypatch):
    at, fake = make_app(monkeypatch)
    at.run()
    at.sidebar.multiselect[0].select("handbook.md").run()
    at.sidebar.slider[0].set_value(3).run()
    at.chat_input[0].set_value("pto?").run()
    assert fake.stream_calls[0]["doc_ids"] == ["d1"] and fake.stream_calls[0]["top_k"] == 3


def test_delete_document_button(monkeypatch):
    at, fake = make_app(monkeypatch)
    at.run()
    next(b for b in at.sidebar.button if b.key == "del_d1").click().run()
    assert fake.deleted == ["d1"] and not at.exception
    assert "handbook.md" not in texts(at.sidebar.markdown)


def test_score_toggle_shows_metric_badges(monkeypatch):
    at, fake = make_app(monkeypatch)
    at.run()
    at.sidebar.toggle[0].set_value(True).run()
    at.chat_input[0].set_value("How many PTO days?").run()
    assert not at.exception and fake.stream_calls[0]["evaluate"] is True
    html = texts(at.chat_message[1].markdown)
    assert "Faithfulness 1.00" in html and "Answer relevancy 0.82" in html and "Context recall —" in html


# ------------------------------------------------------------------ evaluation view
def test_evaluation_view_with_results(monkeypatch):
    at, _ = make_app(monkeypatch, evals=[EVAL_RESULT])
    at.run()
    at.sidebar.radio[0].set_value("📈 Evaluation").run()
    assert not at.exception
    assert len(at.metric) == 5
    assert {m.label for m in at.metric} >= {"Faithfulness", "Overall"} and at.metric[0].value == "1.00"
    assert len(at.dataframe) >= 2  # category summary + results


def test_evaluation_view_empty_state(monkeypatch):
    at, _ = make_app(monkeypatch)
    at.run()
    at.sidebar.radio[0].set_value("📈 Evaluation").run()
    assert not at.exception and any("No evaluation results yet" in i.value for i in at.info)


def test_run_batch_button_starts_batch(monkeypatch):
    at, fake = make_app(monkeypatch, evals=[EVAL_RESULT])
    at.run()
    at.sidebar.radio[0].set_value("📈 Evaluation").run()
    next(b for b in at.button if b.label == "Run batch").click().run()
    assert not at.exception and fake.batches == [(12, "sample set")]
