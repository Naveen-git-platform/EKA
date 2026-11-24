"""In-memory BM25 keyword index built on `rank_bm25`."""
from __future__ import annotations

import math
import threading
from collections.abc import Iterable, Sequence

from rank_bm25 import BM25Okapi

from app.core.text import tokenize
from app.ingestion.models import Chunk


class _PositiveIdfBM25(BM25Okapi):
    """BM25Okapi with the Lucene-style IDF `ln(1 + (N-n+0.5)/(n+0.5))`.

    The stock rank_bm25 IDF goes negative for terms present in more than half of the corpus and
    degenerates on tiny corpora (e.g. a single chunk scores everything <= 0). The Lucene variant is
    always positive, so scores are well-behaved for any corpus size.
    """

    def _calc_idf(self, nd):  # noqa: ANN001
        self.average_idf = 0.0
        for word, freq in nd.items():
            idf = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
            self.idf[word] = idf
            self.average_idf += idf
        self.average_idf /= max(len(nd), 1)


class BM25Index:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None

    def __len__(self) -> int:
        return len(self._chunks)

    def rebuild(self, chunks: Iterable[Chunk]) -> None:
        chunk_list = list(chunks)
        corpus = [tokenize(c.index_text) for c in chunk_list]
        bm25 = _PositiveIdfBM25(corpus) if chunk_list and any(corpus) else None
        with self._lock:
            self._chunks, self._bm25 = chunk_list, bm25

    def search(
        self, query: str, top_k: int, doc_ids: Sequence[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        q_tokens = tokenize(query)
        with self._lock:
            bm25, chunks = self._bm25, self._chunks
        if bm25 is None or not q_tokens:
            return []
        scores = bm25.get_scores(q_tokens)
        allowed = set(doc_ids) if doc_ids else None
        ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        out: list[tuple[Chunk, float]] = []
        for i in ranked:
            if scores[i] <= 0:
                break
            if allowed is not None and chunks[i].doc_id not in allowed:
                continue
            out.append((chunks[i], float(scores[i])))
            if len(out) >= top_k:
                break
        return out
