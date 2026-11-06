"""Turn an uploaded file into per-page text. Uploaded bytes are parsed, never executed."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF

MAGIC_PDF = b"%PDF-"
MAGIC_ZIP = b"PK\x03\x04"
HEADING = re.compile(r"^\s*(chapter|unit|module|section)\s+[\dIVXLC]+[\s:.\-–]*.{0,80}$", re.I | re.M)


class UnsupportedDocument(ValueError):
    pass


@dataclass
class PageText:
    page: int
    text: str
    chapter: str | None = None


@dataclass
class ParsedDocument:
    pages: list[PageText]
    metadata: dict = field(default_factory=dict)


def detect_kind(data: bytes, filename: str) -> str:
    """Decide from content; the extension and client-sent MIME type are not trusted."""
    if data[:5] == MAGIC_PDF:
        return "pdf"
    if data[:4] == MAGIC_ZIP and filename.lower().endswith(".docx"):
        return "docx"
    if filename.lower().endswith(".txt") and b"\x00" not in data[:4096]:
        return "txt"
    raise UnsupportedDocument("Only PDF, TXT and DOCX files are supported")


def parse_document(data: bytes, filename: str) -> ParsedDocument:
    kind = detect_kind(data, filename)
    doc = {"pdf": _pdf, "docx": _docx, "txt": _txt}[kind](data)
    if not any(p.text.strip() for p in doc.pages):
        raise UnsupportedDocument("No text could be extracted. Scanned PDFs need OCR before they can be indexed.")
    doc.metadata["kind"] = kind
    return doc


def _pdf(data: bytes) -> ParsedDocument:
    with fitz.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise UnsupportedDocument("Password-protected PDFs are not supported")
        toc = sorted(((p, title.strip()) for lvl, title, p, *_ in pdf.get_toc() if lvl == 1), key=lambda t: t[0])
        pages, current = [], None
        for i, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True)
            current = _chapter_for(i, toc, text, current)
            pages.append(PageText(page=i, text=text, chapter=current))
        meta = {k: v for k, v in (pdf.metadata or {}).items() if v and k in ("title", "author", "subject")}
        return ParsedDocument(pages=pages, metadata={**meta, "page_count": len(pages), "has_toc": bool(toc)})


def _chapter_for(page: int, toc: list[tuple[int, str]], text: str, current: str | None) -> str | None:
    hits = [title for p, title in toc if p <= page]
    if hits:
        return hits[-1][:300]
    m = HEADING.search(text)
    return m.group(0).strip()[:300] if m else current


def _docx(data: bytes) -> ParsedDocument:
    from docx import Document
    try:
        d = Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedDocument("This DOCX file could not be read") from exc
    pages, buf, chapter, n = [], [], None, 1
    for para in d.paragraphs:
        if para.style is not None and para.style.name.lower().startswith("heading 1"):
            if buf:
                pages.append(PageText(n, "\n".join(buf), chapter)); n += 1; buf = []
            chapter = para.text.strip()[:300]
        if para.text.strip():
            buf.append(para.text)
    if buf:
        pages.append(PageText(n, "\n".join(buf), chapter))
    return ParsedDocument(pages=pages, metadata={"page_count": None})


def _txt(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="replace")
    return ParsedDocument(pages=[PageText(1, text, None)], metadata={"page_count": 1})
