from __future__ import annotations

import time

import pytest

from tests.test_api_query import ask, parse_sse

PTO_DOC = b"# Leave\n\n## PTO\nFull-time employees receive 20 days of PTO every year.\n"


@pytest.fixture
def loaded(api_env):
    client, container, llm = api_env
    container.ingestion.ingest_bytes("handbook.md", PTO_DOC)
    return client, container, llm


def wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


# ------------------------------------------------------------------ POST /evaluate
def test_evaluate_returns_scores_and_stores_them(loaded):
    client, container, _ = loaded
    r = client.post("/evaluate", json={"question": "How many PTO days?", "ground_truth": "20 days per year"})
    assert r.status_code == 200
    body = r.json()
    assert body["faithfulness"] == 1.0 and body["context_precision"] == 1.0 and body["context_recall"] == 1.0
    assert 0 < body["answer_relevancy"] <= 1 and 0 < body["overall"] <= 1
    assert body["answer"].startswith("Full-time employees") and body["contexts"] and body["backend"] == "custom"
    assert body["source"] == "api" and body["errors"] == []
    assert container.eval_store.count() == 1

    got = client.get(f"/evaluations/{body['id']}")
    assert got.status_code == 200 and got.json() == body


def test_evaluate_without_ground_truth(loaded):
    client, _, _ = loaded
    body = client.post("/evaluate", json={"question": "How many PTO days?"}).json()
    assert body["context_recall"] is None and body["faithfulness"] is not None


def test_evaluate_requires_documents(api_env):
    client, _, _ = api_env
    r = client.post("/evaluate", json={"question": "anything?"})
    assert r.status_code == 409 and "upload" in r.json()["detail"].lower()


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "  "}, {"question": "q", "top_k": 99},
                                     {"question": "q", "ground_truth": "x" * 4001}])
def test_evaluate_validation(loaded, payload):
    client, _, _ = loaded
    assert client.post("/evaluate", json=payload).status_code == 422


def test_get_unknown_evaluation_is_404(loaded):
    client, _, _ = loaded
    assert client.get("/evaluations/nope").status_code == 404


# ------------------------------------------------------------------ GET /evaluations
def test_list_evaluations_with_aggregate_and_pagination(loaded):
    client, _, _ = loaded
    empty = client.get("/evaluations").json()
    assert empty["results"] == [] and empty["total"] == 0 and empty["aggregate"]["faithfulness"] is None
    for _ in range(3):
        client.post("/evaluate", json={"question": "How many PTO days?", "ground_truth": "20 days"})
    page = client.get("/evaluations", params={"limit": 2}).json()
    assert page["total"] == 3 and len(page["results"]) == 2
    assert page["aggregate"]["faithfulness"] == 1.0 and page["aggregate"]["count"] == 3.0
    assert len(client.get("/evaluations", params={"limit": 2, "offset": 2}).json()["results"]) == 1
    assert client.get("/evaluations", params={"limit": 0}).status_code == 422


# ------------------------------------------------------------------ batch
def test_batch_with_inline_cases_runs_in_background(loaded):
    client, _, _ = loaded
    cases = [{"question": "How many PTO days?", "ground_truth": "20 days", "id": f"c{i}"} for i in range(3)]
    r = client.post("/evaluate/batch", json={"cases": cases, "name": "inline"})
    assert r.status_code == 202
    run = r.json()
    assert run["status"] in ("running", "completed") and run["total"] == 3 and run["name"] == "inline"

    done = wait_for(lambda: (x := client.get(f"/evaluations/runs/{run['run_id']}").json())["status"] == "completed" and x)
    assert done["completed"] == 3 and done["aggregate"]["faithfulness"] == 1.0
    results = client.get("/evaluations", params={"run_id": run["run_id"]}).json()
    assert results["total"] == 3 and {r["case_id"] for r in results["results"]} == {"c0", "c1", "c2"}
    assert [r["run_id"] for r in client.get("/evaluations/runs").json()["runs"]] == [run["run_id"]]


def test_batch_with_sample_set_and_limit(loaded):
    client, container, _ = loaded
    r = client.post("/evaluate/batch", json={"use_sample": True, "limit": 4})
    assert r.status_code == 202 and r.json()["total"] == 4
    wait_for(lambda: client.get(f"/evaluations/runs/{r.json()['run_id']}").json()["status"] == "completed")
    assert container.eval_store.count(r.json()["run_id"]) == 4


def test_batch_validation_and_errors(loaded, api_env):
    client, container, _ = loaded
    assert client.post("/evaluate/batch", json={}).status_code == 422  # neither source
    assert client.post("/evaluate/batch", json={"use_sample": True, "cases": [{"question": "q"}]}).status_code == 422
    assert client.post("/evaluate/batch", json={"cases": []}).status_code == 422
    assert client.post("/evaluate/batch", json={"cases": [{"question": ""}]}).status_code == 422
    container.settings.eval_questions_path = container.settings.data_dir / "missing.json"
    assert client.post("/evaluate/batch", json={"use_sample": True}).status_code == 404


def test_batch_requires_documents(api_env):
    client, _, _ = api_env
    assert client.post("/evaluate/batch", json={"cases": [{"question": "q?"}]}).status_code == 409


def test_unknown_run_is_404(loaded):
    client, _, _ = loaded
    assert client.get("/evaluations/runs/nope").status_code == 404


# ------------------------------------------------------------------ automatic evaluation after /query
def test_query_with_evaluate_flag_scores_in_background_streaming(loaded):
    client, container, _ = loaded
    frames = parse_sse(ask(client, "How many PTO days?", evaluate=True).text)
    assert frames[-1][0] == "done"
    [res] = wait_for(lambda: container.eval_store.list())[:1] and container.eval_store.list()
    assert res.source == "auto" and res.faithfulness == 1.0 and res.question == "How many PTO days?"
    assert res.contexts and res.answer.startswith("Full-time")


def test_query_with_evaluate_flag_non_streaming(loaded):
    client, container, _ = loaded
    assert ask(client, "How many PTO days?", evaluate=True, stream=False).status_code == 200
    wait_for(lambda: container.eval_store.count() == 1)


def test_query_without_evaluate_flag_stores_nothing(loaded):
    client, container, _ = loaded
    ask(client, "How many PTO days?")
    time.sleep(0.2)
    assert container.eval_store.count() == 0


def test_eval_after_query_setting_enables_it_globally(loaded):
    client, container, _ = loaded
    container.settings.eval_after_query = True
    ask(client, "How many PTO days?")
    wait_for(lambda: container.eval_store.count() == 1)


def test_ungrounded_answers_are_not_auto_evaluated(api_env):
    client, container, _ = api_env  # no documents -> friendly "upload first" message, not a grounded answer
    ask(client, "anything?", evaluate=True)
    time.sleep(0.2)
    assert container.eval_store.count() == 0


# ------------------------------------------------------------------ sample loader
def test_load_samples_endpoint(api_env):
    client, container, _ = api_env
    r = client.post("/samples/load")
    assert r.status_code == 200 and r.json()["indexed"] == 4 and r.json()["failed"] == 0
    assert client.get("/documents").json()["total"] == 4
    again = client.post("/samples/load").json()
    assert {x["status"] for x in again["results"]} == {"duplicate"}
    container.settings.sample_docs_dir = container.settings.data_dir / "nothing-here"
    assert client.post("/samples/load").status_code == 404


def test_openapi_lists_evaluation_endpoints(api_env):
    client, _, _ = api_env
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/evaluate", "/evaluate/batch", "/evaluations", "/evaluations/runs", "/evaluations/{eval_id}",
            "/samples/load"} <= set(paths)
