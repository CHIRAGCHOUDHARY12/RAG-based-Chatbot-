"""
Chunking strategy.

The prospectus is a dense, mixed-structure document: short front-matter
pages, long prose sections, numbered policy clauses, and tabular fee/exam
schedules. Rather than chunk strictly per-page (which would produce wildly
uneven chunk sizes -- some pages have 40 words, others 900) we:

1. Flatten the whole document into a single stream of words while
   remembering which page and which "current heading" every word belongs
   to (the most recently seen heading at that point in the document).
2. Slide a fixed-size window (CHUNK_SIZE_TOKENS words) over that stream
   with overlap (CHUNK_OVERLAP_TOKENS words) so context is not lost at
   chunk boundaries.
3. Tag each chunk with the page number(s) it spans and the nearest
   preceding section heading, which becomes the citation metadata.

This keeps chunks a consistent, embedding-friendly size while preserving
the page-level citation accuracy the product requires (page numbers come
directly from the extraction step, never invented).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.rag.ingestion import PageRecord


@dataclass
class Chunk:
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    section_title: str | None
    content_type: str = "text"


def _word_stream(pages: list[PageRecord]) -> list[tuple[str, int, str | None]]:
    """Return a flat list of (word, page_number, current_heading)."""
    stream: list[tuple[str, int, str | None]] = []
    current_heading: str | None = None
    for page in pages:
        # Update heading as soon as we cross into a page that declares one;
        # if a page has multiple headings we still only track the latest
        # (chunks are page-scale windows, this is a "best effort" label).
        page_heading = current_heading
        words = page.text.split()
        if page.headings:
            # Assign the page's first heading to the words after it appears;
            # simplification: treat the whole page as under its own heading
            # once it has one.
            page_heading = page.headings[0]
        for word in words:
            stream.append((word, page.page_number, page_heading))
        if page.headings:
            current_heading = page.headings[-1]
    return stream


def chunk_pages(
    pages: list[PageRecord],
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    chunk_size = chunk_size or settings.CHUNK_SIZE_TOKENS
    overlap = overlap or settings.CHUNK_OVERLAP_TOKENS
    if overlap >= chunk_size:
        raise ValueError("chunk overlap must be smaller than chunk size")

    stream = _word_stream(pages)
    if not stream:
        return []

    chunks: list[Chunk] = []

    # Preserve front-matter messages as atomic evidence blocks. The normal
    # sliding window is useful for long policy/prose sections, but it can split
    # a 1-page message exactly at the point where the model needs the ending.
    # A dedicated message block lets retrieval return the complete message.
    for page in pages:
        lower = page.text.lower()
        message_specs = (
            ("director, campus of open learning", "DIRECTOR’S MESSAGE", "message_director_full"),
            ("principal, school of open learning", "PRINCIPAL’S MESSAGE", "message_principal_full"),
            ("vice chancellor", "VICE-CHANCELLOR’S MESSAGE", "message_vice_chancellor_full"),
        )
        for signature, title, message_id in message_specs:
            if "dear " not in lower:
                continue
            start = lower.find("dear ")
            if lower.find(signature, start) < 0:
                continue
            end_marker = "university of delhi"
            end = lower.rfind(end_marker, start)
            if end >= 0:
                end += len(end_marker)
                message_text = page.text[start:end].strip()
            else:
                message_text = page.text[start:].strip()
            if message_text:
                chunks.append(
                    Chunk(
                        chunk_id=message_id,
                        text=message_text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_title=title,
                        content_type="message",
                    )
                )
            break

    step = chunk_size - overlap
    idx = 0
    chunk_index = len(chunks)
    n = len(stream)

    while idx < n:
        window = stream[idx: idx + chunk_size]
        if not window:
            break
        text = " ".join(w for w, _, _ in window).strip()
        if text:
            page_numbers = [p for _, p, _ in window]
            headings = [h for _, _, h in window if h]
            section_title = headings[0] if headings else None
            content_type = _classify_chunk_type(text)
            chunks.append(
                Chunk(
                    chunk_id=f"chunk_{chunk_index:05d}",
                    text=text,
                    page_start=min(page_numbers),
                    page_end=max(page_numbers),
                    section_title=section_title,
                    content_type=content_type,
                )
            )
            chunk_index += 1
        if idx + chunk_size >= n:
            break
        idx += step

    return _deduplicate_chunks(chunks)


def _classify_chunk_type(text: str) -> str:
    """Detect strongly table-like chunks using deterministic document cues.

    This is deliberately conservative: it only labels a chunk as a table when
    several structural cues occur together, so normal prose is not forced into
    a tabular answer.
    """
    lower = text.lower()
    cues = 0
    if "s.no" in lower or "s. no" in lower:
        cues += 1
    if "fees in rupees" in lower or "fee structure" in lower:
        cues += 1
    if "semester-i" in lower or "semester-iii" in lower or "type of paper" in lower:
        cues += 1
    if lower.count(" 1 ") + lower.count(" 2 ") + lower.count(" 3 ") >= 3:
        cues += 1
    if "category" in lower and ("total" in lower or "tuition fee" in lower):
        cues += 1
    return "table" if cues >= 2 else "text"


def _deduplicate_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Drop chunks whose text is an exact or near-duplicate of a previous
    chunk (this can happen on pages that are almost entirely boilerplate
    that survived header/footer stripping, e.g. repeated blank forms)."""
    seen: set[str] = set()
    result: list[Chunk] = []
    for c in chunks:
        fingerprint = c.text[:120].lower()
        if fingerprint in seen and len(c.text) < 60:
            continue
        seen.add(fingerprint)
        result.append(c)
    return result
