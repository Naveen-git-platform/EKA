"""LLM clients behind one small async interface.

* `OpenAICompatLLM` - Groq / OpenAI / Together (all speak the OpenAI chat-completions protocol).
* `ScriptedLLM`     - deterministic test double driven by per-task scripts.
* `OfflineLLM`      - heuristic, dependency-free stand-in so the app runs without any API key.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.text import tokenize

logger = get_logger(__name__)

Message = dict[str, str]


class LLMError(RuntimeError):
    """The LLM call failed (network, auth, rate limit, bad response, ...)."""


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        *,
        task: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        task: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...


# ============================================================================ real client
_RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_RETRY_HINT_RE = re.compile(r"try again in (?:(\d+)m)?\s*(\d+(?:\.\d+)?)s", re.IGNORECASE)


class OpenAICompatLLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        *,
        provider: str = "openai",
        temperature: float = 0.1,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_base: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport
        self._backoff = backoff_base

    # ------------------------------------------------------------------ helpers
    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise LLMError(
                f"No API key configured for provider '{self.provider}'. "
                f"Set {self.provider.upper()}_API_KEY in your .env (or use LLM_PROVIDER=fake for offline mode)."
            )
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, messages, *, temperature, max_tokens, json_mode, stream) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature if temperature is None else temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _sleep(self, attempt: int) -> None:
        await asyncio.sleep(min(self._backoff * (2**attempt), 8.0))

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        """Seconds to wait before retrying: the server's own hint if present, else exponential backoff.

        Providers tell us either via a `Retry-After` header or in the message ("Please try again in 3.2s",
        "...in 1m5.5s"). Honouring it matters on rate-limited free tiers. Capped at 30 s.
        """
        backoff = min(self._backoff * (2**attempt), 8.0)
        header = resp.headers.get("retry-after", "")
        try:
            hinted = float(header)
        except ValueError:
            m = _RETRY_HINT_RE.search(self._error_text(resp))
            hinted = (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 0.0
        if hinted <= 0:
            return backoff
        return min(max(hinted + (0.25 if self._backoff else 0.0), backoff), 30.0)

    @staticmethod
    def _error_text(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            msg = body.get("error", body)
            return msg.get("message", str(msg)) if isinstance(msg, dict) else str(msg)
        except Exception:  # noqa: BLE001
            return resp.text[:300]

    # ------------------------------------------------------------------ API
    async def complete(
        self,
        messages: Sequence[Message],
        *,
        task: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        headers = self._headers()
        use_json_mode = json_mode
        last_exc: Exception | None = None
        async with self._client() as client:
            for attempt in range(self.max_retries + 1):
                payload = self._payload(
                    messages, temperature=temperature, max_tokens=max_tokens, json_mode=use_json_mode, stream=False
                )
                try:
                    resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    logger.warning("LLM[%s] network error (attempt %d): %s", task, attempt + 1, exc)
                    if attempt < self.max_retries:
                        await self._sleep(attempt)
                        continue
                    raise LLMError(f"LLM request failed: {exc}") from exc

                if resp.status_code == 400 and use_json_mode and "response_format" in resp.text:
                    use_json_mode = False  # provider/model lacks JSON mode: retry as plain text
                    continue
                if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                    delay = self._retry_delay(resp, attempt)
                    logger.warning("LLM[%s] HTTP %d (attempt %d), retrying in %.1fs", task, resp.status_code,
                                   attempt + 1, delay)
                    await asyncio.sleep(delay)
                    continue
                if resp.status_code >= 400:
                    raise LLMError(f"LLM HTTP {resp.status_code}: {self._error_text(resp)}")
                try:
                    return resp.json()["choices"][0]["message"]["content"] or ""
                except (KeyError, IndexError, ValueError, TypeError) as exc:
                    raise LLMError(f"Malformed LLM response: {resp.text[:200]}") from exc
        raise LLMError(f"LLM request failed after retries: {last_exc}")

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        task: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        headers = self._headers()
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, json_mode=False, stream=True)
        async with self._client() as client:
            for attempt in range(self.max_retries + 1):
                yielded = False
                try:
                    async with client.stream(
                        "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
                    ) as resp:
                        if resp.status_code >= 400:
                            await resp.aread()
                            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                                delay = self._retry_delay(resp, attempt)
                                logger.warning("LLM[%s] stream HTTP %d, retrying in %.1fs",
                                               task, resp.status_code, delay)
                                await asyncio.sleep(delay)
                                continue
                            raise LLMError(f"LLM HTTP {resp.status_code}: {self._error_text(resp)}")
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            try:
                                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                                continue
                            if delta:
                                yielded = True
                                yield delta
                        return
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    if yielded or attempt >= self.max_retries:
                        raise LLMError(f"LLM stream failed: {exc}") from exc
                    await self._sleep(attempt)


# ============================================================================ test double
Script = Callable[[Sequence[Message]], str] | Sequence[str] | str


class ScriptedLLM:
    """Deterministic LLM for tests.

    `scripts` maps a task name (e.g. "planner", "critic", "answer", "*") to either a string, a list of
    strings consumed in order (the last one repeats), a callable `(messages) -> str`, or an Exception
    instance/class to raise. Every call is recorded in `calls`.
    """

    def __init__(self, scripts: dict[str, Any] | None = None, default: str = "{}") -> None:
        self.scripts = dict(scripts or {})
        self.default = default
        self.calls: list[dict[str, Any]] = []
        self._cursor: dict[str, int] = defaultdict(int)

    def calls_for(self, task: str) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["task"] == task]

    def _next(self, task: str, messages: Sequence[Message]) -> str:
        script = self.scripts.get(task, self.scripts.get("*", self.default))
        if isinstance(script, BaseException) or (isinstance(script, type) and issubclass(script, BaseException)):
            raise script if isinstance(script, BaseException) else script("scripted failure")
        if callable(script):
            return script(messages)
        if isinstance(script, str):
            return script
        i = min(self._cursor[task], len(script) - 1)
        self._cursor[task] += 1
        item = script[i]
        if isinstance(item, BaseException):
            raise item
        return item(messages) if callable(item) else item

    async def complete(self, messages, *, task="", json_mode=False, temperature=None, max_tokens=None) -> str:
        self.calls.append({"task": task, "messages": list(messages), "json_mode": json_mode, "stream": False})
        return self._next(task, messages)

    async def stream(self, messages, *, task="", temperature=None, max_tokens=None) -> AsyncIterator[str]:
        self.calls.append({"task": task, "messages": list(messages), "json_mode": False, "stream": True})
        text = self._next(task, messages)
        for piece in re.findall(r"\S+\s*", text):
            await asyncio.sleep(0)
            yield piece


# ============================================================================ offline heuristics
_QUESTION_RE = re.compile(r"QUESTION:\s*(.+?)(?:\n[A-Z_ ]{4,}:|\Z)", re.DOTALL)
_SOURCE_RE = re.compile(r"^\[(\d+)\][^\n]*\n(.*?)(?=^\[\d+\]|\Z)", re.DOTALL | re.MULTILINE)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 3]


class OfflineLLM:
    """Extractive, keyword-overlap 'LLM' used when LLM_PROVIDER=fake. Not intelligent - a keyless demo mode.

    It follows the prompt contracts of the planner / critic / answer / judge stages closely enough that the
    whole pipeline (graph, streaming, API, UI, evaluation) can run end-to-end with no network access.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _last_user(messages: Sequence[Message]) -> str:
        return next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    @staticmethod
    def _question(text: str) -> str:
        m = _QUESTION_RE.search(text)
        return (m.group(1) if m else text).strip()

    @staticmethod
    def _sources(text: str) -> list[tuple[int, str]]:
        return [(int(i), body.strip()) for i, body in _SOURCE_RE.findall(text)]

    def _best_sentences(self, question: str, sources: list[tuple[int, str]], n: int = 2):
        q = set(tokenize(question))
        scored = []
        for idx, body in sources:
            for s in _sentences(body):
                toks = set(tokenize(s))
                overlap = len(q & toks)
                if overlap:
                    scored.append((overlap / (len(q) or 1), idx, s))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:n]

    async def complete(self, messages, *, task="", json_mode=False, temperature=None, max_tokens=None) -> str:
        self.calls.append({"task": task})
        user = self._last_user(messages)
        question = self._question(user)
        if task == "planner":
            return json.dumps({"strategy": "direct", "standalone_query": question, "sub_queries": [question],
                               "reasoning": "Offline mode: single focused search."})
        if task == "critic":
            sources = self._sources(user)
            best = self._best_sentences(question, sources, n=1)
            coverage = round(min(1.0, best[0][0] * 1.5), 2) if best else 0.0
            return json.dumps({
                "sufficient": coverage >= 0.4, "relevance": coverage, "coverage": coverage,
                "relevant_sources": [i for i, _ in sources], "missing_information": "" if coverage >= 0.4 else question,
                "rewritten_queries": [], "reasoning": "Offline keyword-overlap heuristic.",
            })
        if task.startswith("eval_"):
            return await self._judge(task, user)
        return "Offline mode."  # generic fallback

    async def _judge(self, task: str, user: str) -> str:
        """Heuristic judge responses for the evaluation stage (see app/evaluation/prompts.py contracts)."""
        from app.evaluation.offline import offline_judge

        return offline_judge(task, user)

    async def stream(self, messages, *, task="", temperature=None, max_tokens=None) -> AsyncIterator[str]:
        self.calls.append({"task": task})
        user = self._last_user(messages)
        question = self._question(user)
        sources = self._sources(user)
        best = self._best_sentences(question, sources, n=2)
        if best:
            text = " ".join(f"{s.rstrip('.')} [{idx}]." for _, idx, s in best)
        else:
            text = "I could not find enough information in the provided documents to answer that."
        for piece in re.findall(r"\S+\s*", text):
            await asyncio.sleep(0)
            yield piece


# ============================================================================ factory
def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return OfflineLLM()
    return OpenAICompatLLM(
        api_key=settings.llm_api_key,
        model=settings.resolved_llm_model,
        base_url=settings.llm_base_url,
        provider=settings.llm_provider,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
