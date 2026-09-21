"""Fast, deterministic query classification for DocuMind.

The classifier deliberately avoids an LLM call. It selects the response
strategy/format; it never decides factual content.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class QueryPlan:
    kind: str
    max_context: int
    max_output_tokens: int
    direct_extract: bool = False
    output_format: str = "simple"
    completeness_sensitive: bool = False


def _has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_query(question: str) -> QueryPlan:
    q = question.strip()
    l = q.lower()
    words = re.findall(r"\b[\w'-]+\b", l)

    # Full-message requests are completeness-sensitive and should not be
    # summarized. When the user explicitly asks for the full/complete message,
    # prefer deterministic extraction from the indexed message block.
    full_message = _has_any(l, (
        r"\bfull message\b", r"\bcomplete message\b",
        r"\bmessage in full\b", r"\bfull text\b.*\bmessage\b",
        r"\bverbatim\b.*\bmessage\b", r"\bmessage\b.*\bverbatim\b",
    ))
    message_question = _has_any(l, (
        r"\bmessage\b", r"\bdirector'?s message\b",
        r"\bprincipal'?s message\b", r"\bvice[- ]chancellor'?s message\b",
    ))
    if full_message and message_question:
        return QueryPlan("message_full", 16, 4096, True, "simple", True)
    if message_question:
        return QueryPlan("message", 12, 4096, False, "simple", True)

    # Explicitly requested tables and strongly structured document sections.
    # Keep this before generic list/procedure rules so "give the fee structure
    # in a table" is unambiguously routed as a table response.
    explicit_table = _has_any(l, (
        r"\btable\b", r"\btabular\b", r"\brows?\b", r"\bcolumns?\b",
        r"\bin a table\b", r"\bas a table\b", r"\bmake a table\b",
        r"\bformat (?:it|this|the answer) as a table\b",
    ))
    structured_table = _has_any(l, (
        r"\bfee structure\b", r"\bfees? (?:and|&) charges\b",
        r"\bschedule of fees\b", r"\bsemester[- ]wise\b", r"\byear[- ]wise\b",
        r"\bcategory[- ]wise\b", r"\bcourse[- ]wise\b", r"\bsubject[- ]wise\b",
        r"\bprogramme[- ]wise\b", r"\bprogram[- ]wise\b",
        r"\bmembers?\b.*\bdesignation\b", r"\bnames?\b.*\bdesignation\b",
        r"\bdesignation\b.*\bnames?\b",
    ))

    if explicit_table or structured_table:
        return QueryPlan("table", 12, 4096, False, "table", True)

    # Comparisons are naturally easier to read as a table when multiple
    # entities/attributes are requested.
    if re.search(r"\b(compare|difference|different|versus|vs\.?)\b", l):
        return QueryPlan("comparison", 12, 2048, False, "table", True)

    # Vague follow-ups need conversation context and generation.
    if re.search(r"\b(it|this|that|they|them|he|she|him|her|there|above|below)\b", l) and len(words) < 14:
        return QueryPlan("conversation", 6, 768, False, "simple")

    if re.search(r"\b(page|p\.)\s*\d+\b", l):
        return QueryPlan("page", 6, 1024, False, "simple")

    if re.search(r"\b(documents?|requirements?|eligibility|criteria|qualifications?|items?)\b", l):
        return QueryPlan("list", 12, 1536, False, "list", True)

    if re.search(r"\b(how|steps?|procedure|process|apply|application|register)\b", l):
        return QueryPlan("procedure", 12, 2048, False, "list", True)

    if re.search(r"\b(list|documents?|requirements?|eligibility|criteria|qualifications?|items?|which)\b", l):
        return QueryPlan("list", 12, 1536, False, "list", True)

    # Exact factual questions are still generated from retrieved evidence.
    # The old unsafe regex direct-extraction path is intentionally disabled.
    if re.search(r"^(who|what is|what's|when is|when was|where is|where was|which is|what are)\b", l):
        if len(words) <= 12 and not re.search(r"\b(and|also|explain|describe|message|details?|why)\b", l):
            return QueryPlan("exact_fact", 4, 384, False, "simple")
        return QueryPlan("fact", 6, 768, False, "simple")

    if re.search(r"\b(why|explain|describe|summarize|summary|detail|detailed|all about)\b", l):
        return QueryPlan("deep", 8, 2048, False, "simple")

    return QueryPlan("fact", 6, 768, False, "simple")
