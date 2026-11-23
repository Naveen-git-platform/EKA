"""Enterprise Knowledge Agent - Streamlit UI.

Run:  streamlit run frontend/app.py        (backend must be running; set BACKEND_URL if not localhost:8000)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `frontend` importable under `streamlit run`

from frontend import client as api  # noqa: E402
from frontend import helpers as h  # noqa: E402

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
ACCEPTED_TYPES = ["pdf", "docx", "txt", "md", "markdown"]

CSS = """
<style>
  .block-container {padding-top: 2rem; max-width: 1100px;}
  .eka-badge {display:inline-block; padding: 2px 10px; margin: 0 6px 6px 0; border-radius: 999px; font-size: 0.78rem;
              font-weight: 600; border: 1px solid rgba(128,128,128,.35);}
  .eka-good {background: rgba(34,197,94,.15); color: #16a34a;}
  .eka-ok   {background: rgba(245,158,11,.15); color: #d97706;}
  .eka-bad  {background: rgba(239,68,68,.15); color: #dc2626;}
  .eka-na   {background: rgba(128,128,128,.12); color: #888;}
  .eka-source {border-left: 3px solid rgba(99,102,241,.7); padding: 4px 12px; margin: 6px 0; font-size: .92rem;}
  .eka-source mark {background: rgba(250,204,21,.45); color: inherit; padding: 0 2px; border-radius: 3px;}
  .eka-muted {color: #888; font-size: .82rem;}
</style>
"""


# ============================================================================ session / client
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("messages", [])
    ss.setdefault("uploader_key", 0)
    if "client" not in ss:
        ss["client"] = api.EKAClient(BACKEND_URL)


def client() -> api.EKAClient:
    return st.session_state["client"]


# ============================================================================ sidebar
def render_sidebar() -> dict[str, Any]:
    """Draw the sidebar and return the current chat settings."""
    with st.sidebar:
        st.markdown("## 🧠 Knowledge Agent")
        st.caption("Multi-agent RAG · hybrid retrieval · LangGraph")
        view = st.radio("View", ["💬 Chat", "📈 Evaluation"], label_visibility="collapsed", key="view")

        try:
            health = client().health()
        except api.APIError as exc:
            st.error(str(exc))
            st.stop()
        st.session_state["offline"] = health["llm_provider"] == "fake"
        mode = f"{health['llm_provider']} · {health['llm_model']}"
        st.markdown(f"<span class='eka-muted'>LLM: {mode}<br>Embeddings: {health['embedding_provider']}</span>",
                    unsafe_allow_html=True)
        if health["llm_provider"] == "fake":
            st.info("Offline demo mode: no LLM key set, so answers are extractive and evaluation scores are heuristic.")
        elif not health["llm_configured"]:
            st.warning(f"No API key for {health['llm_provider']}. Set it in .env and restart the backend.")

        st.divider()
        st.markdown("#### Documents")
        files = st.file_uploader("Upload documents", type=ACCEPTED_TYPES, accept_multiple_files=True,
                                 key=f"uploader_{st.session_state.uploader_key}", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        if c1.button("Index files", disabled=not files, use_container_width=True):
            do_upload([(f.name, f.getvalue()) for f in files])
        if c2.button("Load samples", use_container_width=True, help="Index the bundled Acme Corp sample documents"):
            do_load_samples()

        try:
            docs = client().list_documents()["documents"]
        except api.APIError as exc:
            st.error(str(exc))
            docs = []
        if not docs:
            st.caption("No documents yet - upload files or load the samples.")
        for d in docs:
            col_a, col_b = st.columns([5, 1])
            col_a.markdown(f"**{d['filename']}**<br><span class='eka-muted'>{d['file_type'].upper()} · "
                           f"{d['chunk_count']} chunks</span>", unsafe_allow_html=True)
            if col_b.button("🗑", key=f"del_{d['doc_id']}", help=f"Delete {d['filename']}"):
                try:
                    client().delete_document(d["doc_id"])
                    st.rerun()
                except api.APIError as exc:
                    st.error(str(exc))

        st.divider()
        st.markdown("#### Settings")
        names = [d["filename"] for d in docs]
        chosen = st.multiselect("Search only in", names, placeholder="All documents")
        top_k = st.slider("Sources per search", 1, 10, 5)
        evaluate = st.toggle("Score each answer", value=False,
                             help="Runs the evaluation pipeline (faithfulness, relevancy, precision) in the background")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    doc_ids = [d["doc_id"] for d in docs if d["filename"] in chosen]
    return {"view": view, "doc_ids": doc_ids, "top_k": top_k, "evaluate": evaluate, "has_docs": bool(docs)}


def do_upload(files: list[tuple[str, bytes]]) -> None:
    try:
        res = client().upload(files)
    except api.APIError as exc:
        st.sidebar.error(f"Upload failed: {exc}")
        return
    for r in res["results"]:
        if r["status"] == "failed":
            st.sidebar.error(f"{r['filename']}: {r['error']}")
        elif r["status"] == "duplicate":
            st.sidebar.info(f"{r['filename']}: already indexed")
        else:
            st.sidebar.success(f"{r['filename']}: {r['status']} ({r['chunk_count']} chunks)")
    st.session_state.uploader_key += 1  # reset the uploader widget
    time.sleep(0.6)
    st.rerun()


def do_load_samples() -> None:
    try:
        client().load_samples()
    except api.APIError as exc:
        st.sidebar.error(str(exc))
        return
    st.rerun()


# ============================================================================ chat view
def render_sources(meta: dict[str, Any], answer: str) -> None:
    cites = meta.get("citations") or []
    sources = meta.get("sources") or []
    if cites:
        st.markdown("**Sources**")
        for c in cites:
            spans = h.supporting_spans(c["text"], answer, c["index"])
            with st.expander(f"[{c['index']}] {h.location(c)}"):
                body = h.highlight_html(c["text"], spans)
                st.markdown(f"<div class='eka-source'>{body}</div>", unsafe_allow_html=True)
                note = " · highlighted: sentence supporting the cited claim" if spans else ""
                st.caption(f"relevance score {c['score']:.3f}{note}")
    others = [s for s in sources if s["index"] not in {c["index"] for c in cites}]
    if others:
        with st.expander(f"Also retrieved ({len(others)})"):
            for s in others:
                st.markdown(f"**[{s['index']}] {h.location(s)}**")
                st.caption(s["snippet"])


def render_trace(meta: dict[str, Any]) -> None:
    plan = meta.get("plan")
    if not plan and not meta.get("retrievals"):
        return
    with st.expander("🔎 How the agents answered", expanded=False):
        if plan:
            fb = " (planner unavailable - used your question as written)" if plan.get("fallback") else ""
            st.markdown(f"**Planner** · `{plan['strategy']}`{fb}")
            for q in plan.get("sub_queries", []):
                st.markdown(f"- {q}")
        for r in meta.get("retrievals", []):
            st.markdown(f"**Retriever** · pass {r['iteration']} · {r['total']} chunks · queries: " +
                        "; ".join(f"`{q}`" for q in r["queries"]))
        for c in meta.get("critiques", []):
            verdict = "✅ sufficient" if c["sufficient"] else "⚠️ insufficient"
            extra = f" → retrying with: {'; '.join(c['rewritten_queries'])}" if c.get("will_retry") else ""
            st.markdown(f"**Critic** · {verdict} · confidence {c['confidence']:.2f}{extra}")
            if c.get("missing_information"):
                st.caption(f"missing: {c['missing_information']}")
        if meta.get("elapsed_ms") is not None:
            st.caption(f"{meta['elapsed_ms'] / 1000:.2f}s · {meta.get('iterations', 1)} retrieval pass(es)")


def render_scores(scores: dict[str, Any] | None) -> None:
    if not scores:
        return
    badges = "".join(h.score_badge_html(h.METRIC_LABELS[m], scores.get(m)) for m in (*h.METRICS, "overall"))
    st.markdown(badges, unsafe_allow_html=True)
    if scores.get("unsupported_claims"):
        with st.expander("Claims the judge could not verify"):
            for c in scores["unsupported_claims"]:
                st.markdown(f"- {c}")


def render_assistant_extras(message: dict[str, Any]) -> None:
    meta = message.get("meta") or {}
    render_trace(meta)
    render_sources(meta, message["content"])
    for e in meta.get("errors", []):
        st.warning(e)
    render_scores(meta.get("scores"))


def run_turn(question: str, cfg: dict[str, Any]) -> None:
    history = h.history_for_backend(st.session_state.messages[:-1])  # everything before this question
    meta: dict[str, Any] = {"plan": None, "retrievals": [], "critiques": [], "citations": [], "sources": [],
                            "errors": [], "elapsed_ms": None, "iterations": 0, "scores": None}
    known_ids: set[str] = set()
    if cfg["evaluate"]:
        try:
            known_ids = {r["id"] for r in client().list_evaluations(limit=10)["results"]}
        except api.APIError:
            pass

    text, final = "", None
    with st.chat_message("assistant"):
        status = st.status("Planning…", expanded=True)
        box = st.empty()
        try:
            for ev in client().stream_query(question, history=history, doc_ids=cfg["doc_ids"] or None,
                                            top_k=cfg["top_k"], evaluate=cfg["evaluate"]):
                kind = ev["type"]
                if kind == "plan":
                    meta["plan"] = ev
                    status.update(label="Searching documents…")
                    queries = "; ".join(f"`{q}`" for q in ev["sub_queries"])
                    status.write(f"**Planner** · `{ev['strategy']}` → {queries}")
                elif kind == "retrieval":
                    meta["retrievals"].append(ev)
                    names = sorted({c["filename"] for c in ev["chunks"] if c.get("filename")})
                    where = ", ".join(names) or "—"
                    status.write(f"**Retriever** · pass {ev['iteration']} · {ev['total']} chunks from {where}")
                    status.update(label="Checking the evidence…")
                elif kind == "critique":
                    meta["critiques"].append(ev)
                    verdict = "sufficient" if ev["sufficient"] else "insufficient"
                    retry = " → searching again" if ev["will_retry"] else ""
                    status.write(f"**Critic** · {verdict} (confidence {ev['confidence']:.2f}){retry}")
                    status.update(label="Searching again…" if ev["will_retry"] else "Writing the answer…")
                elif kind == "token":
                    text += ev["text"]
                    box.markdown(text + "▌")
                elif kind == "citations":
                    meta["citations"], meta["sources"] = ev["citations"], ev["sources"]
                elif kind == "error":
                    meta["errors"].append(f"{ev.get('stage', 'error')}: {ev.get('message', '')}")
                elif kind == "done":
                    final = ev
        except api.APIError as exc:
            meta["errors"].append(str(exc))

        answer = (final or {}).get("answer") or text
        if final:
            meta["elapsed_ms"], meta["iterations"] = final["elapsed_ms"], final["iterations"]
            if final.get("errors") and not final.get("ok"):
                meta["errors"] += [e for e in final["errors"] if e not in "".join(meta["errors"])]
        ok = bool(final and final.get("ok"))
        status.update(label="Done" if ok else "Finished with errors",
                      state="complete" if ok else "error", expanded=False)
        box.markdown(answer or "_No answer was produced._")

        message = {"role": "assistant", "content": answer or "No answer was produced.", "meta": meta}
        if ok and cfg["evaluate"] and meta["citations"]:
            with st.spinner("Scoring answer…"):
                try:
                    meta["scores"] = h.wait_for_evaluation(client().list_evaluations, question, known_ids)
                except api.APIError:
                    pass
        render_assistant_extras(message)
    st.session_state.messages.append(message)


def render_chat(cfg: dict[str, Any]) -> None:
    st.markdown("### Ask your documents")
    if not st.session_state.messages:
        st.caption("Try: *How many PTO days do full-time employees get?* · *What does ERR-5031 mean?* · "
                   "*What happens if a SEV-1 incident exposes EU customer data?*")
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                render_assistant_extras(m)

    question = st.chat_input("Ask a question about your documents…")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        run_turn(question, cfg)


# ============================================================================ evaluation view
def render_evaluation() -> None:
    st.markdown("### Evaluation")
    st.caption("Faithfulness · answer relevancy · context precision · context recall "
               "(LLM-as-judge, Ragas-style definitions)")

    try:
        runs = client().list_runs()["runs"]
    except api.APIError as exc:
        st.error(str(exc))
        return

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        limit = c1.slider("Questions to run", 3, 36, 12, help="From the bundled labelled sample set")
        name = c2.text_input("Run name", value="sample set")
        c3.markdown("<br>", unsafe_allow_html=True)
        if c3.button("Run batch", type="primary", use_container_width=True):
            run_batch(limit, name)

    options = {"All results": None} | {
        f"{r['name'] or r['run_id']} · {r['completed']}/{r['total']} · {r['status']}": r["run_id"] for r in runs
    }
    pick = st.selectbox("Show", list(options))
    run_id = options[pick]
    try:
        data = client().list_evaluations(limit=500, run_id=run_id)
    except api.APIError as exc:
        st.error(str(exc))
        return
    results, agg = data["results"], data["aggregate"]
    if not results:
        st.info("No evaluation results yet. Run a batch above, or turn on **Score each answer** in the chat settings.")
        return

    cols = st.columns(5)
    for col, m in zip(cols, (*h.METRICS, "overall"), strict=True):
        col.metric(h.METRIC_LABELS[m], h.fmt_score(agg.get(m)))
    st.caption(f"{int(agg.get('count') or 0)} evaluated answers · backend: {results[0]['backend']}")
    if st.session_state.get("offline"):
        st.warning("Scores come from the offline heuristic judge - not a quality measure.")

    by_cat = h.aggregate_by_category(results)
    if len(by_cat) > 1 or "uncategorised" not in by_cat:
        st.markdown("**By question category**")
        st.dataframe(
            [{"category": k, "n": int(v["n"]), **{h.METRIC_LABELS[m]: v[m] for m in (*h.METRICS, "overall")}}
             for k, v in by_cat.items()],
            hide_index=True, use_container_width=True,
        )
    st.markdown("**Per metric**")
    st.bar_chart({h.METRIC_LABELS[m]: (agg.get(m) or 0.0) for m in (*h.METRICS, "overall")}, height=220)

    st.markdown("**Results**")
    st.dataframe(h.eval_rows(results), hide_index=True, use_container_width=True)
    labels = [f"{r['created_at'][11:19]} · {r['question'][:80]}" for r in results]
    chosen = st.selectbox("Inspect an answer", range(len(results)), format_func=lambda i: labels[i])
    r = results[chosen]
    with st.expander("Details", expanded=True):
        st.markdown(f"**Q:** {r['question']}")
        if r.get("ground_truth"):
            st.markdown(f"**Reference:** {r['ground_truth']}")
        st.markdown(f"**Answer:** {r['answer'] or '_none_'}")
        render_scores(r)
        for e in r.get("errors") or []:
            st.warning(e)
        with st.expander(f"Retrieved contexts ({len(r['contexts'])})"):
            for i, c in enumerate(r["contexts"], start=1):
                st.markdown(f"**[{i}]** {c}")


def run_batch(limit: int, name: str) -> None:
    try:
        run = client().start_batch(limit=limit, name=name or None)
    except api.APIError as exc:
        st.error(str(exc))
        return
    bar = st.progress(0.0, text="Running batch evaluation…")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            info = client().get_run(run["run_id"])
        except api.APIError as exc:
            st.error(str(exc))
            return
        fraction = min(1.0, info["completed"] / max(info["total"], 1))
        bar.progress(fraction, text=f"{info['completed']}/{info['total']} answers scored")
        if info["status"] != "running":
            break
        time.sleep(1.0)
    st.rerun()


# ============================================================================ main
def main() -> None:
    st.set_page_config(page_title="Enterprise Knowledge Agent", page_icon="🧠", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    cfg = render_sidebar()
    if cfg["view"].endswith("Evaluation"):
        render_evaluation()
    else:
        render_chat(cfg)


main()
