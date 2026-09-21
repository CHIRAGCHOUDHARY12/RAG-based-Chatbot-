"""
Central application configuration.

Every tunable value (paths, model names, chunk sizes, retrieval parameters)
lives here and is sourced from environment variables so the app can be
reconfigured without touching code. See .env.example for the full list.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # --- App -----------------------------------------------------------
    APP_NAME: str = os.getenv("APP_NAME", "DocuMind")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = _env_bool("DEBUG", True)

    # --- Storage ---------------------------------------------------------
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    PDF_DIR: Path = DATA_DIR / "pdf"
    VECTOR_STORE_DIR: Path = Path(
        os.getenv("VECTOR_DB_PATH", str(DATA_DIR / "vector_store"))
    )
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
    DATABASE_PATH: Path = DATA_DIR / "app.db"

    # --- Embeddings --------------------------------------------------------
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))

    # --- Chunking ------------------------------------------------------
    CHUNK_SIZE_TOKENS: int = int(os.getenv("CHUNK_SIZE_TOKENS", "420"))
    CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "80"))

    # --- Retrieval -------------------------------------------------------
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "10"))
    RETRIEVAL_MIN_SCORE: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.18"))
    RERANK_CANDIDATES: int = int(os.getenv("RERANK_CANDIDATES", "80"))
    INDEX_VERSION: int = int(os.getenv("INDEX_VERSION", "5"))
    MAX_EVIDENCE_CHARS: int = int(os.getenv("MAX_EVIDENCE_CHARS", "2400"))
    MAX_SNIPPET_CHARS: int = int(os.getenv("MAX_SNIPPET_CHARS", "700"))

    # --- LLM -----------------------------------------------------------
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-oss:120b-cloud")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    # --- Ollama --------------------------------------------------------
    # OLLAMA_HOST is the current Ollama SDK naming. OLLAMA_URL is retained
    # for backward compatibility with older DocuMind configurations.
    OLLAMA_HOST: str = os.getenv(
        "OLLAMA_HOST",
        os.getenv("OLLAMA_URL", "http://localhost:11434"),
    ).rstrip("/")
    OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "600"))


    # --- Conversation context -------------------------------------------
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "4"))

    # --- Source document ----------------------------------------------
    SOURCE_PDF_NAME: str = os.getenv(
        "SOURCE_PDF_NAME", "UG_Prospectus_2026-27-with_4_year_nw_2.pdf"
    )

    def ensure_directories(self) -> None:
        for path in (self.DATA_DIR, self.PDF_DIR, self.VECTOR_STORE_DIR, self.PROCESSED_DIR):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()

INDEX_VERSION=5
