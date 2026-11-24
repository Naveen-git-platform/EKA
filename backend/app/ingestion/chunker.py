"""Sentence-aware chunking with overlap and stable chunk IDs."""
from __future__ import annotations

import re

from app.ingestion.models import Chunk, Segment

# A unit ends after sentence punctuation + whitespace, or at a newline. Whitespace stays with
# the preceding unit so that "".join(units) == text.
_UNIT_RE = re.compile(r".*?(?:(?<=[.!?])\s+|\n+|$)", re.DOTALL)
_FALLBACK_SEPARATORS = ("; ", ", ", " ")


def _hard_split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _split_long(text: str, size: int, seps: tuple[str, ...] = _FALLBACK_SEPARATORS) -> list[str]:
    """Split a unit that is longer than `size` on the weakest-possible separators."""
    if len(text) <= size:
        return [text]
    if not seps:
        return _hard_split(text, size)
    sep, rest = seps[0], seps[1:]
    if sep not in text:
        return _split_long(text, size, rest)
    parts = text.split(sep)
    pieces = [p + sep for p in parts[:-1]] + [parts[-1]]
    out: list[str] = []
    for piece in pieces:
        out.extend(_split_long(piece, size, rest) if len(piece) > size else [piece])
    return [p for p in out if p]


def _units(text: str, size: int) -> list[str]:
    units: list[str] = []
    for m in _UNIT_RE.finditer(text):
        u = m.group(0)
        if not u:
            continue
        units.extend(_split_long(u, size) if len(u) > size else [u])
    return units


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split `text` into chunks of at most `chunk_size` chars with ~`overlap` chars of carry-over.

    Overlap is made of whole sentence-units taken from the end of the previous chunk, so it never
    exceeds `overlap` characters and never cuts a sentence in half (unless one sentence alone is
    longer than the chunk size).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    current: list[str] = []
    cur_len = 0
    for unit in _units(text, chunk_size):
        if current and cur_len + len(unit) > chunk_size:
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            # keep only a tail of at most `overlap` chars that still leaves room for `unit`
            while current and (cur_len > overlap or cur_len + len(unit) > chunk_size):
                cur_len -= len(current.pop(0))
        current.append(unit)
        cur_len += len(unit)
    tail = "".join(current).strip()
    if tail:
        chunks.append(tail)
    return chunks


def chunk_segments(
    segments: list[Segment],
    *,
    doc_id: str,
    filename: str,
    chunk_size: int,
    overlap: int,
    extra_metadata: dict | None = None,
) -> list[Chunk]:
    """Chunk each segment separately so page/section metadata stays exact."""
    chunks: list[Chunk] = []
    for seg in segments:
        for piece in split_text(seg.text, chunk_size, overlap):
            idx = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}-{idx:04d}",
                    doc_id=doc_id,
                    chunk_index=idx,
                    text=piece,
                    filename=filename,
                    page=seg.page,
                    section=seg.section,
                    metadata={**(extra_metadata or {}), "char_count": len(piece)},
                )
            )
    return chunks
