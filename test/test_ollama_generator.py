import pytest
pytest.importorskip("ollama")
from types import SimpleNamespace

from app.config import settings
from app.rag import generator
from app.rag.retriever import RetrievedChunk


def test_cloud_model_is_configured():
    assert settings.LLM_PROVIDER.lower() == "ollama"
    assert settings.LLM_MODEL == "gpt-oss:120b-cloud"


def test_build_messages_preserves_full_evidence():
    text = "important detail. " * 500
    chunk = RetrievedChunk(
        chunk_id="c1", text=text, page_start=10, page_end=10,
        section_title="TEST SECTION", score=0.95,
    )
    msg = generator.build_messages("Explain the important detail.", [chunk], [])[0]["content"]
    assert text[-100:] in msg


def test_sdk_chat_uses_cloud_model(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, host, timeout):
            calls["host"] = host
            calls["timeout"] = timeout

        def chat(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(message=SimpleNamespace(content="<final>Cloud OK</final>"))

    monkeypatch.setattr(generator, "Client", FakeClient)
    monkeypatch.setattr(generator, "_client", None)
    result = generator.generate_answer_sync("test", [], [])
    assert result == "Cloud OK"
    assert calls["model"] == "gpt-oss:120b-cloud"
    assert calls["stream"] is False
    assert calls["think"] is False
    assert calls["options"]["temperature"] == 0.0


def test_markdown_table_validation():
    assert generator._valid_markdown_table(
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    )
    assert not generator._valid_markdown_table(
        "| A | B |\n|---|---|\n| 1 | 2 | 3 |"
    )


def test_table_prompt_is_selected_for_fee_structure():
    chunk = RetrievedChunk(
        chunk_id="c1", text="Fee Structure Category A 500 300 12070",
        page_start=18, page_end=18, section_title="FEE STRUCTURE", score=0.9,
    )
    msg = generator.build_messages("Give the fee structure in a table", [chunk], [])[0]["content"]
    assert "OUTPUT FORMAT: TABLE" in msg
    assert "valid Markdown table" in msg


def test_requirements_prompt_demands_subordinate_conditions():
    msg = generator.build_messages("What documents are required at the time of admission?", [], [])[0]["content"]
    assert "subordinate notes" in msg
    assert "Do not summarize away a requirement" in msg
