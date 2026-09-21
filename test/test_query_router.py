from app.rag.query_router import classify_query

def test_query_router_uses_direct_mode_for_simple_fact():
    plan = classify_query("Who is the Vice-Chancellor?")
    assert plan.kind == "exact_fact"
    assert plan.direct_extract is False
    assert plan.output_format == "simple"
    assert plan.max_output_tokens <= 512

def test_query_router_uses_deep_mode_only_when_requested():
    plan = classify_query("Explain the complete admission process in detail.")
    assert plan.kind in {"procedure", "deep"}
    assert plan.direct_extract is False


def test_query_router_detects_table_questions():
    assert classify_query("Give the fee structure in a table").output_format == "table"
    assert classify_query("What are the members and their designation?").output_format == "table"
    assert classify_query("Compare Category A and Category B").output_format == "table"
    assert classify_query("What is the total fee for Category A?").output_format == "simple"


def test_document_requirements_questions_are_completeness_sensitive():
    plan = classify_query("What documents are required at the time of admission?")
    assert plan.output_format == "list"
    assert plan.completeness_sensitive is True
    assert plan.max_context >= 12


def test_query_router_detects_explicit_full_message_requests():
    plan = classify_query(
        "Who is director of Campus of Open Learning and what his or her full message"
    )
    assert plan.kind == "message_full"
    assert plan.direct_extract is True
    assert plan.completeness_sensitive is True
    assert plan.max_context >= 16
