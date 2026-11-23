"""HTTP client for the EKA backend (used by the Streamlit UI; has no dependency on the `app` package)."""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

import httpx


class APIError(RuntimeError):
    """The backend returned an error or could not be reached."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def iter_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Incrementally parse Server-Sent Events from an iterable of text lines.

    Yields `(event_name, data_dict)` per frame. Handles comments (`:`), multi-line `data:`, missing `event:`
    (falls back to the payload's own `type`), CRLF, and silently skips frames whose data is not valid JSON.
    """
    event: str | None = None
    data_lines: list[str] = []

    def flush() -> tuple[str, dict[str, Any]] | None:
        nonlocal event, data_lines
        name, raw = event, "\n".join(data_lines)
        event, data_lines = None, []
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return (name or str(payload.get("type", "message")), payload)

    for line in lines:
        line = line.rstrip("\r\n")
        if line == "":
            frame = flush()
            if frame:
                yield frame
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
    frame = flush()  # stream ended without a trailing blank line
    if frame:
        yield frame


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300] or f"HTTP {resp.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail)
    if detail:
        return str(detail)
    results = body.get("results") if isinstance(body, dict) else None
    if results:  # failed upload: surface the per-file error
        errs = [f"{r['filename']}: {r['error']}" for r in results if r.get("error")]
        if errs:
            return "; ".join(errs)
    return f"HTTP {resp.status_code}"


class EKAClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ plumbing
    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise APIError(f"Cannot reach the backend at {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            raise APIError(_error_message(resp), resp.status_code)
        return resp.json()

    # ------------------------------------------------------------------ documents
    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_documents(self) -> dict[str, Any]:
        return self._request("GET", "/documents")

    def upload(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        """Upload `(filename, bytes)` pairs. Raises APIError only if *every* file failed."""
        return self._request("POST", "/upload", files=[("files", (name, data)) for name, data in files])

    def delete_document(self, doc_id: str) -> None:
        self._request("DELETE", f"/documents/{doc_id}")

    def load_samples(self) -> dict[str, Any]:
        return self._request("POST", "/samples/load")

    # ------------------------------------------------------------------ query
    def stream_query(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        doc_ids: list[str] | None = None,
        top_k: int | None = None,
        evaluate: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Yield agent events (plan / retrieval / critique / token / citations / error / done) as they arrive."""
        body: dict[str, Any] = {"question": question, "history": history or [], "evaluate": evaluate, "stream": True}
        if doc_ids:
            body["doc_ids"] = doc_ids
        if top_k:
            body["top_k"] = top_k
        try:
            with self._http.stream("POST", "/query", json=body) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise APIError(_error_message(resp), resp.status_code)
                for _, payload in iter_sse(resp.iter_lines()):
                    yield payload
        except httpx.HTTPError as exc:
            raise APIError(f"Connection to the backend was lost: {exc}") from exc

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, question: str, ground_truth: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/evaluate", json={"question": question, "ground_truth": ground_truth or None})

    def list_evaluations(self, limit: int = 50, run_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if run_id:
            params["run_id"] = run_id
        return self._request("GET", "/evaluations", params=params)

    def list_runs(self, limit: int = 20) -> dict[str, Any]:
        return self._request("GET", "/evaluations/runs", params={"limit": limit})

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/evaluations/runs/{run_id}")

    def start_batch(self, *, limit: int | None = None, name: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/evaluate/batch", json={"use_sample": True, "limit": limit, "name": name})
