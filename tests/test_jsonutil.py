from __future__ import annotations

from app.core.jsonutil import extract_json, extract_json_object


def test_plain_object():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_code_fence_and_prose():
    text = 'Sure! Here you go:\n```json\n{"strategy": "direct", "sub_queries": ["x"]}\n```\nHope that helps.'
    assert extract_json_object(text) == {"strategy": "direct", "sub_queries": ["x"]}


def test_prose_around_object_without_fence():
    assert extract_json_object('The result is {"ok": true} as requested') == {"ok": True}


def test_trailing_commas_repaired():
    assert extract_json_object('{"a": [1, 2,], "b": 3,}') == {"a": [1, 2], "b": 3}


def test_braces_inside_strings_do_not_confuse_matching():
    assert extract_json_object('x {"q": "what is {this} } thing", "n": 1} y') == {"q": "what is {this} } thing", "n": 1}


def test_nested_objects():
    assert extract_json_object('{"a": {"b": {"c": 1}}} trailing') == {"a": {"b": {"c": 1}}}


def test_array_extraction():
    assert extract_json('result: ["a", "b"]') == ["a", "b"]
    assert extract_json_object('["a"]') is None  # arrays are not objects


def test_garbage_returns_none():
    for bad in ("", "no json here", "{broken", "{'single': 'quotes'}", None):
        assert extract_json_object(bad) is None  # type: ignore[arg-type]


def test_first_valid_object_wins():
    assert extract_json_object('{"a": 1} {"b": 2}') == {"a": 1}
