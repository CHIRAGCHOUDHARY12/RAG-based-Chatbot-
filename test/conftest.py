import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database.db import init_db  # noqa: E402


@pytest.fixture()
def temp_data_dir(monkeypatch):
    """Point the app at a throwaway data directory for the duration of a test."""
    tmpdir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(settings, "DATA_DIR", tmpdir)
    monkeypatch.setattr(settings, "PDF_DIR", tmpdir / "pdf")
    monkeypatch.setattr(settings, "VECTOR_STORE_DIR", tmpdir / "vector_store")
    monkeypatch.setattr(settings, "PROCESSED_DIR", tmpdir / "processed")
    monkeypatch.setattr(settings, "DATABASE_PATH", tmpdir / "app.db")
    settings.ensure_directories()
    init_db()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)
