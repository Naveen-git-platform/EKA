from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.jsonutil import extract_json_object
from app.core.llm import LLMError, OfflineLLM, OpenAICompatLLM, ScriptedLLM, build_llm

MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


def ok_body(text="hello"):
    return {"choices": [{"message": {"content": text}}]}


def make(handler, **kw) -> OpenAICompatLLM:
    return OpenAICompatLLM("sk-test", "m1", "https://api.example.com/v1", transport=httpx.MockTransport(handler),
                           backoff_base=0.0, **kw)


async def collect(agen) -> list[str]:
    return [x async for x in agen]


# ------------------------------------------------------------------ complete()
async def test_complete_request_shape_and_parsing():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=ok_body("answer text"))

    out = await make(handler, temperature=0.3).complete(MSGS, json_mode=True, max_tokens=50)
    assert out == "answer text"
    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "m1" and seen["body"]["temperature"] == 0.3 and seen["body"]["stream"] is False
    assert seen["body"]["response_format"] == {"type": "json_object"} and seen["body"]["max_tokens"] == 50
    assert seen["body"]["messages"] == MSGS


async def test_temperature_override_and_no_json_mode():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_body())

    await make(handler).complete(MSGS, temperature=0.0)
    assert seen["body"]["temperature"] == 0.0 and "response_format" not in seen["body"]


async def test_json_mode_unsupported_falls_back_to_plain():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format is not supported"}})
        return httpx.Response(200, json=ok_body("plain"))

    assert await make(handler).complete(MSGS, json_mode=True) == "plain"
    assert len(bodies) == 2 and "response_format" not in bodies[1]


async def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=ok_body("finally"))

    assert await make(handler, max_retries=3).complete(MSGS) == "finally"
    assert calls["n"] == 3


async def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    with pytest.raises(LLMError, match="503"):
        await make(handler, max_retries=2).complete(MSGS)
    assert calls["n"] == 3  # 1 try + 2 retries


async def test_auth_error_is_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    with pytest.raises(LLMError, match="Invalid API key"):
        await make(handler, max_retries=3).complete(MSGS)
    assert calls["n"] == 1


async def test_network_error_retried_then_raises():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(LLMError, match="request failed"):
        await make(handler, max_retries=1).complete(MSGS)
    assert calls["n"] == 2


async def test_malformed_response_raises():
    with pytest.raises(LLMError, match="Malformed"):
        await make(lambda req: httpx.Response(200, json={"unexpected": True})).complete(MSGS)


async def test_missing_api_key_message_mentions_provider():
    llm = OpenAICompatLLM("", "m", provider="groq")
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        await llm.complete(MSGS)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        await collect(llm.stream(MSGS))


# ------------------------------------------------------------------ stream()
def sse(*pieces, done=True) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n" for p in pieces]
    lines.insert(1, ": keep-alive comment\n\n")
    lines.insert(1, f"data: {json.dumps({'choices': [{'delta': {}}]})}\n\n")  # role-only delta
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


async def test_stream_yields_tokens_in_order():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=sse("Hel", "lo ", "world"), headers={"content-type": "text/event-stream"})

    assert await collect(make(handler).stream(MSGS)) == ["Hel", "lo ", "world"]
    assert seen["body"]["stream"] is True


async def test_stream_retries_5xx_before_first_token():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": {"message": "oops"}})
        return httpx.Response(200, content=sse("ok"))

    assert await collect(make(handler, max_retries=2).stream(MSGS)) == ["ok"]
    assert calls["n"] == 2


async def test_stream_http_error_raises():
    with pytest.raises(LLMError, match="401"):
        await collect(make(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}})).stream(MSGS))


async def test_stream_network_error_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, content=sse("recovered"))

    assert await collect(make(handler, max_retries=2).stream(MSGS)) == ["recovered"]


# ------------------------------------------------------------------ ScriptedLLM
async def test_scripted_sequences_callables_and_errors():
    llm = ScriptedLLM({
        "a": ["first", "second"],
        "b": lambda msgs: f"echo:{msgs[-1]['content']}",
        "c": LLMError("nope"),
        "*": "wildcard",
    })
    assert [await llm.complete(MSGS, task="a") for _ in range(3)] == ["first", "second", "second"]  # last repeats
    assert await llm.complete(MSGS, task="b") == "echo:hi"
    with pytest.raises(LLMError):
        await llm.complete(MSGS, task="c")
    assert await llm.complete(MSGS, task="zzz") == "wildcard"
    assert len(llm.calls_for("a")) == 3


async def test_scripted_sequence_can_contain_exceptions_and_streams():
    llm = ScriptedLLM({"x": [LLMError("first fails"), "then ok words"]})
    with pytest.raises(LLMError):
        await llm.complete(MSGS, task="x")
    assert "".join(await collect(llm.stream(MSGS, task="x"))) == "then ok words"


# ------------------------------------------------------------------ OfflineLLM + factory
async def test_offline_llm_contracts():
    llm = OfflineLLM()
    plan = extract_json_object(await llm.complete(
        [{"role": "user", "content": "QUESTION: What is the minimum password length?"}], task="planner"))
    assert plan["sub_queries"] == ["What is the minimum password length?"]

    sources = "[1] sec.docx (section: Passwords)\nPasswords must be at least 14 characters long.\n\n[2] faq.txt\nPlans start at $12."
    user = f"QUESTION: minimum password length\n\nSEARCHES ALREADY TRIED: (none)\n\nSOURCES:\n{sources}"
    critique = extract_json_object(await llm.complete([{"role": "user", "content": user}], task="critic"))
    assert critique["sufficient"] is True and critique["relevant_sources"] == [1, 2]

    answer = "".join(await collect(llm.stream([{"role": "user", "content": user}], task="answer")))
    assert "14 characters" in answer and "[1]" in answer

    no_match = "QUESTION: kubernetes helm charts\n\nSOURCES:\n[1] a.txt\nUnrelated text about lunch."
    assert "could not find" in "".join(await collect(llm.stream([{"role": "user", "content": no_match}], task="answer")))
    crit2 = extract_json_object(await llm.complete([{"role": "user", "content": no_match}], task="critic"))
    assert crit2["sufficient"] is False


def test_build_llm_factory():
    assert isinstance(build_llm(Settings(_env_file=None, llm_provider="fake")), OfflineLLM)
    g = build_llm(Settings(_env_file=None, llm_provider="groq", groq_api_key="k"))
    assert isinstance(g, OpenAICompatLLM)
    assert g.base_url == "https://api.groq.com/openai/v1" and g.model == "llama-3.3-70b-versatile"
    o = build_llm(Settings(_env_file=None, llm_provider="openai", openai_api_key="k", llm_model="gpt-4o"))
    assert o.base_url == "https://api.openai.com/v1" and o.model == "gpt-4o"
