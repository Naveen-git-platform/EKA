from __future__ import annotations

from app.core.text import tokenize
from app.ingestion.models import Chunk
from app.retrieval.bm25 import BM25Index


def mk(i: int, text: str, doc: str = "d1", section: str | None = None) -> Chunk:
    return Chunk(chunk_id=f"{doc}-{i:04d}", doc_id=doc, chunk_index=i, text=text, filename=f"{doc}.txt", section=section)


CORPUS = [
    mk(0, "Employees accrue twenty days of paid vacation each year."),
    mk(1, "Error ERR-5031 means the database connection pool is exhausted."),
    mk(2, "Passwords must be at least fourteen characters long."),
    mk(3, "Meals are reimbursed up to seventy five dollars per day while traveling.", doc="d2"),
]


def test_tokenizer_keeps_identifiers_and_parts():
    toks = tokenize("Error ERR-5031 in SEC-POL-014")
    assert "err-5031" in toks and "err" in toks and "5031" in toks
    assert "sec-pol-014" in toks
    assert "in" not in toks  # stopword


def test_stemming_matches_plurals_and_inflections():
    assert tokenize("Passwords expire") == tokenize("password expired")
    assert tokenize("days policies") == tokenize("day policy")
    assert tokenize("ERR-5031") == ["err-5031", "err", "5031"]  # digit-bearing tokens are never stemmed
    assert tokenize("class access") == ["class", "access"]  # 'ss' endings preserved


def test_exact_identifier_match_ranks_first():
    idx = BM25Index()
    idx.rebuild(CORPUS)
    hits = idx.search("what is ERR-5031", top_k=3)
    assert hits[0][0].chunk_id == "d1-0001"
    assert hits[0][1] > 0


def test_keyword_ranking():
    idx = BM25Index()
    idx.rebuild(CORPUS)
    assert idx.search("password length characters", 1)[0][0].chunk_id == "d1-0002"
    assert idx.search("vacation days", 1)[0][0].chunk_id == "d1-0000"


def test_no_match_returns_empty():
    idx = BM25Index()
    idx.rebuild(CORPUS)
    assert idx.search("kubernetes helm chart", 5) == []


def test_empty_index_and_empty_query():
    idx = BM25Index()
    assert idx.search("anything", 5) == []
    idx.rebuild(CORPUS)
    assert idx.search("", 5) == []
    assert idx.search("the of and", 5) == []  # only stopwords
    idx.rebuild([])
    assert len(idx) == 0 and idx.search("vacation", 5) == []


def test_top_k_bounds_results():
    idx = BM25Index()
    idx.rebuild([mk(i, f"shared keyword number {i}") for i in range(10)])
    assert len(idx.search("shared keyword", 3)) == 3
    assert len(idx.search("shared keyword", 100)) == 10


def test_doc_filter():
    idx = BM25Index()
    idx.rebuild(CORPUS)
    hits = idx.search("per day meals", 5, doc_ids=["d2"])
    assert [c.doc_id for c, _ in hits] == ["d2"]
    assert idx.search("vacation", 5, doc_ids=["d2"]) == []


def test_single_chunk_corpus_scores_positive():
    idx = BM25Index()
    idx.rebuild([mk(0, "only one chunk about vacation policy")])
    hits = idx.search("vacation", 3)
    assert len(hits) == 1 and hits[0][1] > 0


def test_term_in_every_chunk_still_scores_positive():
    idx = BM25Index()
    idx.rebuild([mk(i, f"policy text {i}") for i in range(4)])
    assert all(score > 0 for _, score in idx.search("policy", 4))


def test_section_title_is_searchable():
    idx = BM25Index()
    idx.rebuild([mk(0, "Fourteen characters minimum.", section="Passwords and Authentication"), mk(1, "Other body text.")])
    assert idx.search("authentication", 1)[0][0].chunk_id == "d1-0000"


def test_rebuild_replaces_contents():
    idx = BM25Index()
    idx.rebuild(CORPUS)
    idx.rebuild([mk(0, "completely different content about rockets")])
    assert idx.search("vacation", 5) == []
    assert len(idx.search("rockets", 5)) == 1
