"""
PDF ingestion: turns a PDF file into a list of per-page, cleaned text
records with lightweight structural metadata (detected section headings).

We use pdfplumber for extraction. It handles the text layer of this kind
of typeset document (a university prospectus) reliably, and lets us
inspect per-character font size, which we use to spot headings without
needing a heavier layout model.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PageRecord:
    page_number: int  # 1-indexed
    text: str
    headings: list[str]  # headings detected on this page, in order


_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _detect_repeated_lines(pages_raw_lines: list[list[str]], min_page_fraction: float = 0.35) -> set[str]:
    """Find lines (typically headers/footers) that recur across a large
    fraction of pages, so we can strip them out and stop them polluting
    every chunk with boilerplate."""
    counts: Counter[str] = Counter()
    total_pages = max(len(pages_raw_lines), 1)
    for lines in pages_raw_lines:
        seen_this_page = set()
        for line in lines:
            key = line.strip()
            if not key or len(key) > 90:
                continue
            if key in seen_this_page:
                continue
            seen_this_page.add(key)
            counts[key] += 1
    threshold = max(3, int(total_pages * min_page_fraction))
    return {line for line, count in counts.items() if count >= threshold}


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    # Numbered section headings, e.g. "8.9 Sports Excellence and Incentive Policy"
    if re.match(r"^\d{1,2}(\.\d{1,2})?\s+[A-Za-z]", stripped):
        return True
    # Mostly-uppercase short lines, e.g. "VISION & MISSION", "PREAMBLE"
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.85 and len(letters) >= 4:
        return True
    return False


def extract_pages(pdf_path: Path) -> list[PageRecord]:
    """Extract cleaned text and detected headings for every page of the PDF."""
    raw_pages_text: list[str] = []
    raw_pages_lines: list[list[str]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            raw_pages_text.append(text)
            raw_pages_lines.append(text.split("\n"))

    repeated_lines = _detect_repeated_lines(raw_pages_lines)

    records: list[PageRecord] = []
    for idx, lines in enumerate(raw_pages_lines):
        page_number = idx + 1
        kept_lines: list[str] = []
        headings: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                kept_lines.append(line)
                continue
            if stripped in repeated_lines:
                continue  # drop recurring header/footer boilerplate
            if _looks_like_heading(stripped):
                headings.append(stripped)
            kept_lines.append(line)
        cleaned = _normalize_text("\n".join(kept_lines))
        records.append(PageRecord(page_number=page_number, text=cleaned, headings=headings))

    return records


class PdfExtractionError(Exception):
    pass


def extract_pdf_safely(pdf_path: Path) -> list[PageRecord]:
    if not pdf_path.exists():
        raise PdfExtractionError(f"PDF not found at {pdf_path}")
    try:
        records = extract_pages(pdf_path)
    except Exception as exc:  # pdfplumber/pdfminer can raise various errors on bad PDFs
        raise PdfExtractionError(f"Failed to extract text from PDF: {exc}") from exc
    if not any(r.text.strip() for r in records):
        raise PdfExtractionError(
            "No extractable text found in PDF. It may be a scanned/image-only document "
            "that requires OCR, which this pipeline does not perform."
        )
    return records
