"""
Local vector store.

Rather than depend on a full vector-database server (Chroma/FAISS both
work well, but pull in extra native dependencies that can be finicky to
install on some systems), we implement a small, transparent, file-backed
store: embeddings live in a single numpy array, metadata lives alongside
in JSON. For a single document with a few hundred chunks this scales
comfortably -- similarity search is one matrix-vector multiply -- while
keeping the whole implementation auditable in ~100 lines.

Persisted layout inside VECTOR_STORE_DIR:
    vectors.npy      -- float32 array, shape (n_chunks, dim), L2-normalized
    metadata.json     -- list of per-chunk metadata dicts, same order as vectors
    manifest.json      -- fingerprint of the source PDF used to build the index
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import settings


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    section_title: str | None
    score: float
    content_type: str = "text"


class VectorStoreError(Exception):
    pass


class VectorStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or settings.VECTOR_STORE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
        self._vectors_path = self.directory / "vectors.npy"
        self._metadata_path = self.directory / "metadata.json"
        self._manifest_path = self.directory / "manifest.json"
        self._vectors: np.ndarray | None = None
        self._metadata: list[dict] | None = None

    # -- persistence ------------------------------------------------------

    def exists(self) -> bool:
        return self._vectors_path.exists() and self._metadata_path.exists()

    def build(self, vectors: np.ndarray, metadata: list[dict], manifest: dict) -> None:
        if vectors.shape[0] != len(metadata):
            raise VectorStoreError("vector count and metadata count must match")
        np.save(self._vectors_path, vectors.astype("float32"))
        self._metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False),
            encoding="utf-8",
        )

        self._manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))
        self._vectors = vectors
        self._metadata = metadata

    def load(self) -> None:
        if not self.exists():
            raise VectorStoreError("Vector store has not been built yet.")
        self._vectors = np.load(self._vectors_path)
        self._metadata = json.loads(self._metadata_path.read_text(encoding="utf-8"))

    def read_manifest(self) -> dict | None:
        if not self._manifest_path.exists():
            return None
        return json.loads(self._manifest_path.read_text(encoding="utf-8"))

    # -- search -------------------------------------------------------

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self._vectors is None or self._metadata is None:
            self.load()
        assert self._vectors is not None and self._metadata is not None

        if self._vectors.shape[0] == 0:
            return []

        # Vectors and query are both L2-normalized, so the dot product is
        # exactly the cosine similarity.
        scores = self._vectors @ query_vector
        top_k = min(top_k, len(scores))
        top_indices = np.argpartition(-scores, top_k - 1)[:top_k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]

        results = []
        for i in top_indices:
            meta = self._metadata[int(i)]
            results.append(
                SearchResult(
                    chunk_id=meta["chunk_id"],
                    text=meta["text"],
                    page_start=meta["page_start"],
                    page_end=meta["page_end"],
                    section_title=meta.get("section_title"),
                    score=float(scores[int(i)]),
                    content_type=meta.get("content_type", "text"),
                )
            )
        return results

    def lexical_candidates(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Cheap in-memory lexical retrieval over indexed chunk metadata.

        This avoids reopening/reparsing the PDF on every question.
        """
        if self._vectors is None or self._metadata is None:
            self.load()
        assert self._metadata is not None
        import re
        q = query.lower().replace("’", "'").replace("-", " ")
        qwords = {w for w in re.findall(r"\w+", q) if len(w) > 2}
        if not qwords:
            return []
        scored = []
        for meta in self._metadata:
            text = str(meta.get("text", "")).lower().replace("’", "'").replace("-", " ")
            section = str(meta.get("section_title") or "").lower()
            tw = set(re.findall(r"\w+", text))
            overlap = len(qwords & tw) / len(qwords)
            phrase = 1.0 if q.strip() and q.strip() in text else 0.0
            heading = len(qwords & set(re.findall(r"\w+", section))) / len(qwords)
            score = 0.58 * overlap + 0.22 * heading + 0.20 * phrase
            if score > 0.03:
                scored.append((score, meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchResult(
                chunk_id=m["chunk_id"], text=m["text"],
                page_start=m["page_start"], page_end=m["page_end"],
                section_title=m.get("section_title"), score=float(score),
                content_type=m.get("content_type", "text")
            )
            for score, m in scored[:limit]
        ]

    def count(self) -> int:
        if self._metadata is None:
            if not self.exists():
                return 0
            self.load()
        return len(self._metadata or [])

