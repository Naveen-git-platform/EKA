from __future__ import annotations

import pytest

from app.ingestion.errors import (
    CorruptDocumentError,
    EmptyDocumentError,
    UnsupportedFileTypeError,
)
from app.ingestion.loaders import load_document, load_markdown, load_text
from tests.helpers import make_docx, make_pdf


# ------------------------------------------------------------------ TXT
def test_txt_utf8():
    segs = load_document("a.txt", "Hello wörld.\r\nSecond line.".encode())
    assert len(segs) == 1
    assert "wörld" in segs[0].text and "\r" not in segs[0].text


def test_txt_utf16_and_cp1252():
    assert "naïve" in load_text("naïve café".encode("utf-16"))[0].text
    assert "café" in load_text("café".encode("cp1252"))[0].text


def test_txt_whitespace_only_is_empty():
    with pytest.raises(EmptyDocumentError):
        load_document("a.txt", b"   \n\n \t ")


def test_zero_bytes_is_empty():
    with pytest.raises(EmptyDocumentError):
        load_document("a.md", b"")


# ------------------------------------------------------------------ Markdown
MD = b"""Intro text before any heading.

# Policy
Top level body.

## Leave
Leave details.

### Parental
Parental details.

## Expenses
Expense details.

# Appendix
Appendix body.
"""


def test_markdown_heading_paths():
    segs = {s.section: s.text for s in load_markdown(MD)}
    assert segs[None].startswith("Intro text")
    assert segs["Policy"] == "Top level body."
    assert segs["Policy > Leave"] == "Leave details."
    assert segs["Policy > Leave > Parental"] == "Parental details."
    assert segs["Policy > Expenses"] == "Expense details."  # sibling pops the deeper heading
    assert segs["Appendix"] == "Appendix body."


def test_markdown_code_fence_hash_is_not_heading():
    md = b"# Real\ntext\n```\n# not a heading\nprint(1)\n```\nmore\n"
    segs = load_markdown(md)
    assert [s.section for s in segs] == ["Real"]
    assert "# not a heading" in segs[0].text


def test_markdown_extension_variants():
    assert load_document("x.markdown", b"# T\nbody")[0].section == "T"


# ------------------------------------------------------------------ DOCX
def test_docx_sections_and_table():
    data = make_docx(
        [("Security", ["Use MFA everywhere."]), ("Devices", ["Encrypt disks."])],
        title="Policy Doc",
        table=[["Level", "Owner"], ["Restricted", "CISO"]],
    )
    segs = load_document("p.docx", data)
    by_section = {s.section: s.text for s in segs}
    assert by_section["Policy Doc > Security"] == "Use MFA everywhere."
    assert "Encrypt disks." in by_section["Policy Doc > Devices"]
    assert "Restricted | CISO" in by_section["Policy Doc > Devices"]  # table appended to last section


def test_docx_corrupt():
    with pytest.raises(CorruptDocumentError):
        load_document("bad.docx", b"this is not a zip file")


def test_docx_without_text_is_empty():
    with pytest.raises(EmptyDocumentError):
        load_document("blank.docx", make_docx([]))


# ------------------------------------------------------------------ PDF
def test_pdf_pages_numbered():
    segs = load_document("r.pdf", make_pdf(["First page text", "Second page text"]))
    assert [(s.page, s.text) for s in segs] == [(1, "First page text"), (2, "Second page text")]


def test_pdf_skips_blank_pages_but_keeps_page_numbers():
    segs = load_document("r.pdf", make_pdf(["One", "", "Three"]))
    assert [s.page for s in segs] == [1, 3]


def test_pdf_corrupt():
    with pytest.raises(CorruptDocumentError):
        load_document("bad.pdf", b"%PDF-1.4 garbage that is not a pdf")


def test_pdf_with_no_text_is_empty():
    with pytest.raises(EmptyDocumentError):
        load_document("blank.pdf", make_pdf(["", ""]))


# ------------------------------------------------------------------ dispatch
def test_unsupported_extension():
    with pytest.raises(UnsupportedFileTypeError):
        load_document("notes.xlsx", b"data")


def test_no_extension():
    with pytest.raises(UnsupportedFileTypeError):
        load_document("README", b"data")


def test_extension_case_insensitive():
    assert load_document("A.TXT", b"hello")[0].text == "hello"
