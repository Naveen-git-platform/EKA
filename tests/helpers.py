"""Test helpers: build small real DOCX / PDF files in memory."""
from __future__ import annotations

import io


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
