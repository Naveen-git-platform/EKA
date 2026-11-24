"""Test helpers: build small real DOCX / PDF files in memory, plus a concept-based embedder."""
from __future__ import annotations

import io
import math

from app.core.text import stem_token, tokenize


class ConceptEmbedder:
    """Toy *semantic* embedder: one dimension per concept, words map to concepts via a lexicon.

    Words outside the lexicon (e.g. rare identifiers like ERR-5031) are invisible to it, which mimics how
    dense models blur exact identifiers; synonyms in a lexicon entry land on the same dimension, which
    mimics paraphrase matching. That lets tests show where BM25 and vectors each win.
    """

    def __init__(self, concepts: dict[str, list[str]]) -> None:
        self._names = list(concepts)
        self._lex: dict[str, int] = {}
        for i, name in enumerate(self._names):
            for w in concepts[name]:
                self._lex[stem_token(w.lower())] = i

    @property
    def dim(self) -> int:
        return len(self._names)

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            if tok in self._lex:
                vec[self._lex[tok]] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return [1.0 / math.sqrt(self.dim)] * self.dim  # "no idea" -> uniform vector
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


CONCEPTS = {
    "timeoff": ["pto", "vacation", "holiday", "leave", "time-off", "allowance"],
    "incident": ["incident", "outage", "pool", "limiter", "database"],
    "security": ["password", "mfa", "credential", "login", "authentication"],
    "expenses": ["meal", "reimburse", "expense", "travel", "spending"],
}

CONCEPT_DOCS = {
    "pto.txt": "Full-time employees receive 20 days of PTO every year. Unused PTO expires in January.",
    "err5031.txt": "ERR-5031 means the connection pool is exhausted. Restart the affected pods.",
    "err4290.txt": "ERR-4290 means the rate limiter is misconfigured. Check the gateway settings.",
    "pw.txt": "Passwords must be at least 14 characters long. MFA is mandatory for every login.",
    "meals.txt": "Meals are reimbursed up to $75 per day while traveling on company business.",
}


def make_docx(sections: list[tuple[str, list[str]]], title: str | None = None, table: list[list[str]] | None = None) -> bytes:
    from docx import Document

    doc = Document()
    if title:
        doc.add_heading(title, level=0)
    for heading, paras in sections:
        if heading:
            doc.add_heading(heading, level=1)
        for p in paras:
            doc.add_paragraph(p)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pdf(pages: list[str]) -> bytes:
    """One line of text per page (use short strings)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        if text:
            c.drawString(72, 750, text)
        c.showPage()
    c.save()
    return buf.getvalue()
