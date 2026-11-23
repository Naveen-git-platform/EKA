"""Small helpers shared by all agents."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def get_emitter() -> Callable[[dict[str, Any]], None]:
    """Return LangGraph's custom-stream writer, or a no-op when an agent runs outside a graph.

    Agents call `emit({...})` to push events (plan, retrieval, tokens, ...) to whoever is streaming the graph.
    """
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except Exception:  # noqa: BLE001 - not inside a graph run (e.g. unit tests)
        return lambda _event: None


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "1", "sufficient"}:
            return True
        if v in {"false", "no", "0", "insufficient"}:
            return False
    if isinstance(value, int | float):
        return bool(value)
    return default


def as_unit_float(value: Any, default: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return max(0.0, min(1.0, f))


def clean_str_list(value: Any, limit: int, max_len: int = 300) -> list[str]:
    """Normalise an LLM-provided list of strings: strip, drop empties, dedupe (case-insensitive), cap."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        s = " ".join(item.split())[:max_len]
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= limit:
            break
    return out
