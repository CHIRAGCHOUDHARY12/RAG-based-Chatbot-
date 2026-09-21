from app.rag.retriever import _expand_complete_sections
from app.rag.vector_store import SearchResult


class FakeStore:
    def __init__(self):
        self._metadata = [
            {"chunk_id": "c1", "text": "item 1", "page_start": 1, "page_end": 1, "section_title": "2.4 Documents", "content_type": "text"},
            {"chunk_id": "c2", "text": "item 2 and note", "page_start": 2, "page_end": 2, "section_title": "2.4 Documents", "content_type": "text"},
            {"chunk_id": "c3", "text": "other", "page_start": 3, "page_end": 3, "section_title": "Other", "content_type": "text"},
        ]

    def load(self):
        return None


def test_expand_complete_section_adds_sibling_chunks():
    ranked = [SearchResult("c1", "item 1", 1, 1, "2.4 Documents", 0.9, "text")]
    expanded = _expand_complete_sections("What documents are required?", ranked, FakeStore(), 4)
    assert [r.chunk_id for r in expanded] == ["c1", "c2"]


def test_admission_document_section_is_prioritized():
    from app.rag.retriever import _rerank
    results = [
        SearchResult("other", "documents identity card", 171, 172, "8.6 Identity Card", 0.8, "text"),
        SearchResult("docs", "2.4 Documents to be uploaded at the time of Admission", 25, 26, "2.4 Documents to be uploaded at the time of Admission.", 0.5, "text"),
    ]
    ranked = _rerank("What documents are required at the time of admission?", results)
    assert ranked[0].chunk_id == "docs"


def test_message_page_is_preserved_as_atomic_block():
    from app.rag.chunking import chunk_pages
    from app.rag.ingestion import PageRecord

    page = PageRecord(
        page_number=5,
        text=(
            "Dear Students,\n"
            "This is the complete message.\n"
            "Best Wishes!!\n"
            "Prof. Payal Mago\n"
            "Director, Campus of Open Learning\n"
            "University of Delhi"
        ),
        headings=["DIRECTOR’S MESSAGE"],
    )
    chunks = chunk_pages([page], chunk_size=20, overlap=5)
    message = next(c for c in chunks if c.chunk_id == "message_director_full")
    assert message.content_type == "message"
    assert message.page_start == message.page_end == 5
    assert message.text.startswith("Dear Students,")
    assert message.text.endswith("University of Delhi")
