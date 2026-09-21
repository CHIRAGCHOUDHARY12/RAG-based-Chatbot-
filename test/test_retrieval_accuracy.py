import pytest
pytest.importorskip("ollama")
from pathlib import Path

from app.config import settings
from app.rag.retriever import retrieve
from app.rag.vector_store import VectorStore


def test_vice_chancellor_query_prioritizes_message_page():
    pdf = settings.PDF_DIR / settings.SOURCE_PDF_NAME
    if not pdf.exists():
        candidates = sorted(settings.PDF_DIR.glob("*.pdf"))
        if not candidates:
            return
    results = retrieve(
        "who is VICE-CHANCELLOR and what is VICE-CHANCELLOR'S MESSAGE",
        VectorStore(),
    )
    assert results
    assert results[0].page_start == 4
    assert "Prof. Yogesh Singh" in results[0].text
    assert "VICE-CHANCELLOR" in results[0].text


def test_director_query_prioritizes_director_message_page():
    results = retrieve(
        "who is director and what is director's message",
        VectorStore(),
    )
    assert results
    assert results[0].page_start == 5
    assert "Prof. Payal Mago" in results[0].text
    assert "DIRECTOR" in results[0].text


def test_long_negative_answer_is_flagged_for_repair():
    from app.rag.generator import _needs_answer_repair
    from app.rag.retriever import RetrievedChunk

    chunk = RetrievedChunk(
        chunk_id="page_0004",
        text=(
            "VICE-CHANCELLOR’S MESSAGE Prof. Yogesh Singh Vice Chancellor "
            "University of Delhi. A warm welcome to all!"
        ),
        page_start=4,
        page_end=4,
        section_title="VICE-CHANCELLOR’S MESSAGE",
        score=0.89,
    )
    bad_answer = (
        "The document does not contain a Vice-Chancellor's message. "
        "I could not identify a current Vice-Chancellor in the document. "
        "The available material instead discusses policies and administrative matters."
    )
    assert _needs_answer_repair(bad_answer, [chunk]) is True


def test_generator_keeps_full_evidence_for_accuracy():
    from app.rag.generator import build_messages
    from app.rag.retriever import RetrievedChunk

    long_text = "Authoritative evidence " + ("important detail. " * 500)
    chunk = RetrievedChunk(
        chunk_id="c1", text=long_text, page_start=10, page_end=10,
        section_title="TEST SECTION", score=0.95,
    )
    msg = build_messages("Explain the important detail.", [chunk], [])
    content = msg[0]["content"]
    assert "important detail." in content
    assert long_text[-100:] in content


def test_simple_fact_does_not_use_unsafe_regex_extraction():
    from app.rag.generator import stream_answer
    from app.rag.retriever import RetrievedChunk
    # The generator should route even simple questions through the grounded
    # answer engine rather than guessing a person's name from a regex.
    assert not hasattr(__import__("app.rag.generator", fromlist=["x"]), "_direct_extract")
