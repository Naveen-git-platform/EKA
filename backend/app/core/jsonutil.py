"""Tolerant JSON extraction for LLM output (code fences, prose around the object, trailing commas)."""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _balanced_blobs(text: str, open_ch: str, close_ch: str) -> Iterator[str]:
    """Yield each balanced `open_ch ... close_ch` span (string/escape aware), scanning start positions in order."""
    start = text.find(open_ch)
    while start != -1:
        depth, in_str, esc = 0, False, False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            yield text[start : end + 1]
            start = text.find(open_ch, end + 1)
        else:
            start = text.find(open_ch, start + 1)


def _try_parse(blob: str) -> Any | None:
    for attempt in (blob, _TRAILING_COMMA_RE.sub(r"\1", blob)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    return None


def extract_json(text: str) -> Any | None:
    """Return the first JSON object/array found in `text`, or None if nothing parses."""
    if not text:
        return None
    for cand in [text, *_FENCE_RE.findall(text)]:
        cand = cand.strip()
        # earliest-starting structure wins, so objects before arrays only if they appear first
        found: list[tuple[int, Any]] = []
        for opener, closer in (("{", "}"), ("[", "]")):
            for blob in _balanced_blobs(cand, opener, closer):
                parsed = _try_parse(blob)
                if parsed is not None:
                    found.append((cand.find(blob), parsed))
                    break
        if found:
            return min(found, key=lambda t: t[0])[1]
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """First JSON *object* in `text` (skips arrays and unparseable braces)."""
    if not text:
        return None
    for cand in [text, *_FENCE_RE.findall(text)]:
        for blob in _balanced_blobs(cand.strip(), "{", "}"):
            parsed = _try_parse(blob)
            if isinstance(parsed, dict):
                return parsed
    return None
