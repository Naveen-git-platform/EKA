from __future__ import annotations

import pytest

from frontend import helpers as h

ANSWER = "Full-time employees receive 20 days of PTO [1]. Unused days carry over up to 5 days [1][2]. Meals are capped at $75 [3]."
SOURCE_1 = "Full-time employees accrue 20 days of paid time off (PTO) per calendar year. Part-time staff accrue in proportion."
SOURCE_2 = "Up to 5 unused PTO days carry over into the next year. Anything above 5 days expires on January 31."


def test_score_formatting_and_levels():
    assert h.fmt_score(None) == "—" and h.fmt_score(0.856) == "0.86" and h.fmt_score(0) == "0.00"
    assert [h.score_level(v) for v in (None, 1.0, 0.8, 0.79, 0.5, 0.49, 0.0)] == ["na", "good", "good", "ok", "ok", "bad", "bad"]
    badge = h.score_badge_html("Faith <b>", 0.9)
    assert "eka-good" in badge and "0.90" in badge and "<b>" not in badge  # label is escaped


def test_location_formatting():
    assert h.location({"filename": "a.pdf", "page": 2, "section": "Policy > Leave > PTO"}) == "a.pdf · p.2 · PTO"
    assert h.location({"filename": "a.md"}) == "a.md"
    assert h.location({}) == "document"


def test_claims_citing_extracts_sentences_per_source():
    assert h.claims_citing(ANSWER, 1) == ["Full-time employees receive 20 days of PTO .", "Unused days carry over up to 5 days ."]
    assert h.claims_citing(ANSWER, 2) == ["Unused days carry over up to 5 days ."]
    assert h.claims_citing(ANSWER, 3) == ["Meals are capped at $75 ."]
    assert h.claims_citing(ANSWER, 9) == []


def test_supporting_spans_pick_the_relevant_source_sentence():
    assert h.supporting_spans(SOURCE_1, ANSWER, 1)[0].startswith("Full-time employees accrue 20 days")
    spans2 = h.supporting_spans(SOURCE_2, ANSWER, 2)
    assert spans2 and spans2[0].startswith("Up to 5 unused PTO days carry over")
    assert h.supporting_spans("Totally unrelated words here.", ANSWER, 1) == []
    assert h.supporting_spans(SOURCE_1, "No citations here.", 1) == []


def test_highlight_html_marks_spans_and_escapes_everything_else():
    out = h.highlight_html("Use <script>alert(1)</script> & MFA. Rotate keys.", ["Use <script>alert(1)</script> & MFA."])
    assert out.startswith("<mark>Use &lt;script&gt;alert(1)&lt;/script&gt; &amp; MFA.</mark>")
    assert "<script>" not in out and out.endswith(" Rotate keys.")
    assert h.highlight_html("plain\ntext", []) == "plain<br>text"
    assert h.highlight_html("abc", ["zzz"]) == "abc"  # span not found -> untouched


def test_highlight_html_overlapping_spans_do_not_corrupt_output():
    out = h.highlight_html("alpha beta gamma", ["alpha beta", "beta gamma"])
    assert out.count("<mark>") == 1 and "gamma" in out


def test_history_for_backend_keeps_recent_turns_and_strips_metadata():
    msgs = [{"role": "user", "content": f"q{i}", "meta": {"x": 1}} if i % 2 == 0 else {"role": "assistant", "content": f"a{i}"}
            for i in range(20)]
    msgs.append({"role": "assistant", "content": ""})  # empty messages are dropped
    msgs.append({"role": "system", "content": "ignored"})
    hist = h.history_for_backend(msgs, max_messages=4)
    assert hist == [{"role": "user", "content": "q16"}, {"role": "assistant", "content": "a17"},
                    {"role": "user", "content": "q18"}, {"role": "assistant", "content": "a19"}]


def test_wait_for_evaluation_returns_new_matching_result():
    calls = {"n": 0}

    def list_fn(limit):
        calls["n"] += 1
        results = [{"id": "old", "question": "q?"}]
        if calls["n"] >= 3:
            results.insert(0, {"id": "new", "question": "q?"})
        return {"results": results}

    sleeps = []
    got = h.wait_for_evaluation(list_fn, "q?", {"old"}, sleep=sleeps.append, interval=0.5)
    assert got["id"] == "new" and calls["n"] == 3 and sleeps == [0.5, 0.5]


def test_wait_for_evaluation_times_out_and_ignores_other_questions():
    t = {"now": 0.0}

    def clock():
        return t["now"]

    def sleep(s):
        t["now"] += s

    def list_fn(limit):
        return {"results": [{"id": "x", "question": "different question"}]}

    assert h.wait_for_evaluation(list_fn, "q?", set(), timeout=2.0, interval=1.0, sleep=sleep, clock=clock) is None
    assert t["now"] >= 2.0


def test_eval_rows_and_category_aggregate():
    results = [
        {"created_at": "2026-01-01T10:00:00+00:00", "question": "q1", "category": "keyword", "faithfulness": 1.0,
         "overall": 0.9, "source": "batch", "errors": []},
        {"created_at": "2026-01-01T10:00:01+00:00", "question": "q2", "category": "keyword", "faithfulness": None,
         "overall": 0.5, "source": "batch", "errors": ["e"]},
        {"created_at": "2026-01-01T10:00:02+00:00", "question": "q3", "faithfulness": 0.5, "overall": 0.4, "source": "api"},
    ]
    rows = h.eval_rows(results)
    assert rows[0]["time"] == "2026-01-01 10:00:00" and rows[1]["errors"] == 1 and rows[2]["category"] == ""
    agg = h.aggregate_by_category(results)
    assert agg["keyword"]["faithfulness"] == 1.0 and agg["keyword"]["overall"] == 0.7 and agg["keyword"]["n"] == 2.0
    assert agg["uncategorised"]["faithfulness"] == 0.5 and agg["uncategorised"]["context_recall"] is None


@pytest.mark.parametrize("v", [0.0, 0.5, 1.0])
def test_badge_for_boundary_values(v):
    assert "eka-" in h.score_badge_html("x", v)
