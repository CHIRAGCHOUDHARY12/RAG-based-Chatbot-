"""
Dependency-light local embeddings.

This implementation intentionally avoids sentence-transformers/PyTorch
because native PyTorch DLLs are blocked by the Windows Code Integrity
policy on this machine.

HashingVectorizer produces a deterministic sparse text representation,
which we convert to a dense, L2-normalized float32 array so the existing
VectorStore can continue using cosine similarity via dot products.

The public API remains:
    embed_texts(texts)
    embed_query(text)
"""

from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from app.config import settings


class EmbeddingError(Exception):
    pass


_vectorizer: HashingVectorizer | None = None


def _get_vectorizer() -> HashingVectorizer:
    global _vectorizer

    if _vectorizer is None:
        try:
            _vectorizer = HashingVectorizer(
                n_features=settings.EMBEDDING_DIM,
                alternate_sign=False,
                norm=None,
                lowercase=True,
                strip_accents="unicode",
                ngram_range=(1, 2),
            )
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to initialize embedding vectorizer: {exc}"
            ) from exc

    return _vectorizer


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a batch of texts.

    Returns:
        (n, EMBEDDING_DIM) float32 array, L2-normalized so that
        dot product == cosine similarity.
    """
    if not texts:
        return np.zeros(
            (0, settings.EMBEDDING_DIM),
            dtype="float32",
        )

    vectorizer = _get_vectorizer()

    try:
        sparse_vectors = vectorizer.transform(texts)

        # Normalize rows to unit length. This preserves the existing
        # VectorStore assumption that dot product == cosine similarity.
        normalized = normalize(
            sparse_vectors,
            norm="l2",
            axis=1,
            copy=False,
        )

        vectors = normalized.toarray().astype("float32")

    except Exception as exc:
        raise EmbeddingError(
            f"Failed to generate embeddings: {exc}"
        ) from exc

    return vectors


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]
