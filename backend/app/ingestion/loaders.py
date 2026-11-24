"""Document loaders: PDF, DOCX, TXT, Markdown -> list[Segment]."""
from __future__ import annotations

import io
import re
from pathlib import PurePath

from app.core.logging import get_logger
from app.ingestion.errors import (
    CorruptDocumentError,
    EmptyDocumentError,
    UnsupportedFileTypeError,
)
from app.ingestion.models import Segment

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def file_extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def _decode_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_text(data: bytes) -> list[Segment]:
    text = _normalize(_decode_text(data))
    return [Segment(text=text)] if text else []


class _SectionCollector:
    """Accumulates body lines under a heading path and emits Segments."""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.path: list[tuple[int, str]] = []
        self.buf: list[str] = []

    def heading(self, level: int, title: str) -> None:
        self.flush()
        while self.path and self.path[-1][0] >= level:
            self.path.pop()
        self.path.append((level, title))

    def flush(self) -> None:
        body = _normalize("\n".join(self.buf))
        if body:
            section = " > ".join(t for _, t in self.path) or None
            self.segments.append(Segment(text=body, section=section))
        self.buf.clear()


def load_markdown(data: bytes) -> list[Segment]:
    """Split on headings; each segment carries its heading path as `section`."""
    text = _decode_text(data).replace("\r\n", "\n").replace("\r", "\n")
    col = _SectionCollector()
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            col.buf.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        if m:
            col.heading(len(m.group(1)), m.group(2).strip())
        else:
            col.buf.append(line)
    col.flush()
    return col.segments


def load_pdf(data: bytes) -> list[Segment]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise CorruptDocumentError("PDF is password-protected")
        segments: list[Segment] = []
        for page_no, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            # PDF text wraps at line width: join single newlines, keep blank-line paragraph breaks.
            raw = re.sub(r"(?<!\n)\n(?!\n)", " ", raw.replace("\r", ""))
            body = _normalize(raw)
            if body:
                segments.append(Segment(text=body, page=page_no))
        return segments
    except CorruptDocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many exception types on bad input
        raise CorruptDocumentError(f"Could not parse PDF: {exc}") from exc


def load_docx(data: bytes) -> list[Segment]:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - zipfile/lxml/KeyError on bad files
        raise CorruptDocumentError(f"Could not parse DOCX: {exc}") from exc

    col = _SectionCollector()
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name if para.style is not None else "") or ""
        m = re.match(r"Heading (\d)", style)
        if m or style == "Title":
            col.heading(int(m.group(1)) if m else 0, text)
        else:
            col.buf.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                col.buf.append(" | ".join(cells))
    col.flush()
    return col.segments


_LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".txt": load_text,
    ".md": load_markdown,
    ".markdown": load_markdown,
}


def load_document(filename: str, data: bytes) -> list[Segment]:
    """Parse raw bytes into segments, raising typed errors on failure."""
    ext = file_extension(filename)
    loader = _LOADERS.get(ext)
    if loader is None:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext or filename}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if not data:
        raise EmptyDocumentError(f"'{filename}' is empty")
    segments = loader(data)
    if not segments:
        raise EmptyDocumentError(f"No extractable text found in '{filename}'")
    logger.info("Parsed %s into %d segment(s)", filename, len(segments))
    return segments
