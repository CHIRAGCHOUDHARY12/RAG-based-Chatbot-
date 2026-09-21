"""
Orchestrates the full ingest-once, reuse-after pipeline:

    PDF -> extract -> clean -> chunk -> embed -> persist vector store

On startup we compute a fingerprint of the source PDF (path + size +
mtime) and compare it against what's recorded in the vector store's
manifest. If they match, we skip re-indexing entirely and just load the
existing store. This means restarting the app is fast, and swapping in a
new/updated PDF is automatically detected.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.rag.chunking import chunk_pages
from app.rag.embeddings import embed_texts
from app.rag.ingestion import PdfExtractionError, extract_pdf_safely
from app.rag.vector_store import VectorStore, VectorStoreError

logger = logging.getLogger("rag.pipeline")


@dataclass
class IndexStatus:
    ready: bool
    chunk_count: int
    source_pdf: str
    message: str


def _fingerprint(pdf_path: Path) -> str:
    stat = pdf_path.stat()
    raw = f"{pdf_path.name}:{stat.st_size}:{int(stat.st_mtime)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def find_source_pdf() -> Path | None:
    """Locate the PDF to index: prefer the configured filename, otherwise
    fall back to the first PDF found in data/pdf/."""
    preferred = settings.PDF_DIR / settings.SOURCE_PDF_NAME
    if preferred.exists():
        return preferred
    candidates = sorted(settings.PDF_DIR.glob("*.pdf"))
    return candidates[0] if candidates else None


def is_index_current(pdf_path: Path, store: VectorStore) -> bool:
    if not store.exists():
        return False
    manifest = store.read_manifest()
    if not manifest:
        return False

    # Rebuild automatically when retrieval/indexing parameters that affect
    # the stored chunks or embeddings have changed. The old implementation
    # checked only the PDF fingerprint, so changing chunk size/overlap or
    # embedding model could leave the application using a stale index.
    return (
        manifest.get("index_version") == settings.INDEX_VERSION
        and manifest.get("fingerprint") == _fingerprint(pdf_path)
        and manifest.get("embedding_model") == settings.EMBEDDING_MODEL
        and manifest.get("embedding_dim") == settings.EMBEDDING_DIM
        and manifest.get("chunk_size_tokens") == settings.CHUNK_SIZE_TOKENS
        and manifest.get("chunk_overlap_tokens") == settings.CHUNK_OVERLAP_TOKENS
    )


def build_index(pdf_path: Path, store: VectorStore) -> int:
    """Run the full ingestion pipeline and persist the result. Returns the
    number of chunks indexed."""
    logger.info("Extracting text from %s", pdf_path.name)
    pages = extract_pdf_safely(pdf_path)

    logger.info("Chunking %d pages", len(pages))
    chunks = chunk_pages(pages)
    if not chunks:
        raise PdfExtractionError("Document produced zero chunks after cleaning; nothing to index.")

    logger.info("Embedding %d chunks", len(chunks))
    vectors = embed_texts([c.text for c in chunks])

    metadata = [
        {
            "chunk_id": c.chunk_id,
            "text": c.text,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "section_title": c.section_title,
            "content_type": c.content_type,
        }
        for c in chunks
    ]
    manifest = {
        "source_pdf": pdf_path.name,
        "index_version": settings.INDEX_VERSION,
        "fingerprint": _fingerprint(pdf_path),
        "chunk_count": len(chunks),
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dim": settings.EMBEDDING_DIM,
        "chunk_size_tokens": settings.CHUNK_SIZE_TOKENS,
        "chunk_overlap_tokens": settings.CHUNK_OVERLAP_TOKENS,
    }

    logger.info("Persisting vector store to %s", store.directory)
    store.build(vectors, metadata, manifest)
    return len(chunks)


def ensure_index(force_rebuild: bool = False) -> IndexStatus:
    """Called on startup (and available for a manual '/admin/reindex').
    Builds the index only if it's missing or stale relative to the PDF."""
    pdf_path = find_source_pdf()
    if pdf_path is None:
        return IndexStatus(
            ready=False,
            chunk_count=0,
            source_pdf="",
            message=f"No PDF found in {settings.PDF_DIR}. Add a PDF there and restart.",
        )

    store = VectorStore()

    if not force_rebuild and is_index_current(pdf_path, store):
        store.load()
        return IndexStatus(
            ready=True,
            chunk_count=store.count(),
            source_pdf=pdf_path.name,
            message="Loaded existing vector index (document unchanged since last index).",
        )

    try:
        count = build_index(pdf_path, store)
    except (PdfExtractionError, VectorStoreError) as exc:
        logger.error("Indexing failed: %s", exc)
        return IndexStatus(ready=False, chunk_count=0, source_pdf=pdf_path.name, message=str(exc))

    return IndexStatus(
        ready=True,
        chunk_count=count,
        source_pdf=pdf_path.name,
        message=f"Indexed {count} chunks from {pdf_path.name}.",
    )
