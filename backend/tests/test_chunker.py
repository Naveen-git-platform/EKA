from __future__ import annotations

import re

import pytest

from app.ingestion.chunker import chunk_segments, split_text
from app.ingestion.models import Segment

SENTENCES = [f"This is sentence number {i} about topic {i % 7} and it has some padding words." for i in range(60)]
LONG = " ".join(SENTENCES)


@pytest.mark.parametrize("size,overlap", [(200, 0), (200, 50), (300, 80), (500, 120), (120, 40), (80, 79)])
def test_invariants(size, overlap):
    chunks = split_text(LONG, size, overlap)
    assert chunks, "expected chunks"
    for c in chunks:
        assert 0 < len(c) <= size, f"chunk of {len(c)} exceeds {size}"
        assert c == c.strip()
    # every sentence must be fully present in at least one chunk (no text lost) unless a sentence is
    # itself longer than the chunk size.
    for s in SENTENCES:
        if len(s) <= size:
            assert any(s in c for c in chunks), f"lost sentence: {s}"


def test_overlap_is_shared_text_and_bounded():
    chunks = split_text(LONG, 300, 100)
    assert len(chunks) > 3
    shared_any = False
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        # longest suffix of prev that is a prefix of nxt
        k = max((k for k in range(1, min(len(prev), len(nxt)) + 1) if prev.endswith(nxt[:k])), default=0)
        assert k <= 100
        shared_any = shared_any or k > 0
    assert shared_any, "expected at least some overlap between consecutive chunks"


def test_zero_overlap_has_no_repeats():
    chunks = split_text(LONG, 300, 0)
    joined = " ".join(chunks)
    for s in SENTENCES:
        assert joined.count(s) == 1


def test_short_text_single_chunk():
    assert split_text("Just one short sentence.", 800, 100) == ["Just one short sentence."]


def test_empty_and_whitespace():
    assert split_text("", 100, 10) == []
    assert split_text("   \n  ", 100, 10) == []


def test_unbroken_string_is_hard_split():
    chunks = split_text("x" * 1000, 100, 10)
    assert all(len(c) <= 100 for c in chunks)
    assert sum(len(c) for c in chunks) >= 1000


def test_long_sentence_without_punctuation_splits_on_commas_or_spaces():
    text = ", ".join(f"item{i}" for i in range(200))
    chunks = split_text(text, 100, 20)
    assert all(len(c) <= 100 for c in chunks)
    assert "item0" in chunks[0] and "item199" in chunks[-1]


def test_paragraph_breaks_kept_as_boundaries():
    text = "Para one sentence.\n\nPara two sentence.\n\nPara three sentence."
    chunks = split_text(text, 25, 0)
    assert chunks == ["Para one sentence.", "Para two sentence.", "Para three sentence."]


def test_no_infinite_loop_when_overlap_close_to_size():
    chunks = split_text(LONG, 100, 99)
    assert chunks and all(len(c) <= 100 for c in chunks)


@pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (100, 100), (100, -1), (100, 150)])
def test_invalid_params(size, overlap):
    with pytest.raises(ValueError):
        split_text("text", size, overlap)


def test_chunk_segments_metadata_ids_and_determinism():
    segs = [
        Segment(text=" ".join(SENTENCES[:10]), page=1, section="Intro"),
        Segment(text=" ".join(SENTENCES[10:20]), page=2, section="Intro > Details"),
    ]
    kwargs = dict(doc_id="abc123", filename="f.pdf", chunk_size=250, overlap=50, extra_metadata={"file_type": "pdf"})
    a = chunk_segments(segs, **kwargs)
    b = chunk_segments(segs, **kwargs)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]  # deterministic
    assert len({c.chunk_id for c in a}) == len(a)  # unique
    assert [c.chunk_index for c in a] == list(range(len(a)))  # sequential
    assert all(re.fullmatch(r"abc123-\d{4}", c.chunk_id) for c in a)
    pages = {c.page for c in a}
    assert pages == {1, 2}
    assert all((c.section == "Intro") == (c.page == 1) for c in a)  # metadata not mixed across segments
    assert all(c.metadata["file_type"] == "pdf" and c.metadata["char_count"] == len(c.text) for c in a)
    assert all(c.filename == "f.pdf" and c.doc_id == "abc123" for c in a)


def test_index_text_includes_section():
    c = chunk_segments([Segment(text="Body text.", section="Policy > Leave")], doc_id="d", filename="f.md",
                       chunk_size=100, overlap=10)[0]
    assert c.index_text == "Policy > Leave\nBody text."
    c2 = chunk_segments([Segment(text="Body text.")], doc_id="d", filename="f.md", chunk_size=100, overlap=10)[0]
    assert c2.index_text == "Body text."
