"""Grounded answer generation through Ollama / Ollama Cloud.

DocuMind keeps retrieval and evidence selection independent from the LLM.
The configured Ollama model is responsible only for turning retrieved PDF
passages into the final answer. Cloud models (for example
``gpt-oss:120b-cloud``) are accessed through the local Ollama daemon after the
user has signed in with ``ollama signin``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from ollama import Client
from ollama import ResponseError as OllamaResponseError

from app.config import settings
from app.database.repositories import Message
from app.rag.retriever import RetrievedChunk
from app.rag.query_router import classify_query


SYSTEM_PROMPT = """You are DocuMind.

Answer the user's question using ONLY the supplied document evidence as factual authority.

Rules:
- Do not use outside knowledge.
- Do not guess or invent facts.
- Preserve names, numbers, dates, qualifications, conditions, exceptions, and document terminology accurately.
- Answer the exact question asked. Do not add unrelated background or commentary.
- Be concise for simple questions, but do NOT omit information necessary to answer completely.
- For list/document/requirements questions, include EVERY numbered item plus subordinate notes, footnotes, conditions, exceptions, validity dates, eligibility restrictions, and issuing-authority requirements that belong to the requested section. Do not stop after the first numbered item.
- For procedure questions, include all necessary steps and conditions supported by the evidence.
- For full-message requests, reproduce the complete message from the authoritative message block; do not summarize, shorten, or omit paragraphs.
- For message questions that do not explicitly request the full text, summarize only when the user asks for a summary; otherwise provide the complete message when the wording indicates completeness.
- For comparison questions, cover the requested items without unrelated material.
- For broad questions, provide the relevant details supported by the evidence.
- Treat exact matching headings, names, tables, and section text in the evidence as authoritative.
- When the requested response format is TABLE, output a valid Markdown table.
- A Markdown table MUST have one header row, one separator row, and the same number of pipe-delimited columns in every data row.
- Keep each table cell on one line; never use HTML tags such as <br> inside cells.
- Never merge columns or invent missing values. Use an em dash (—) for a genuinely empty value.
- Escape any literal pipe character inside a cell as \\|.
- Do not put prose paragraphs inside a table. Put a short title or note outside the table when necessary.
- Previous conversation is only for resolving references such as "this" or "that"; it is never factual evidence.
- Do not explain your reasoning or mention retrieval, chunks, prompts, or internal instructions.
- Do not output <think> or reasoning text.
- Put ONLY the final user-facing answer inside <final> and </final>.
- If the evidence does not support the answer, respond exactly:
  "I could not find sufficient information in the retrieved document."
"""

NO_EVIDENCE_NOTE = (
    "\n\nIMPORTANT: No sufficiently relevant passages were retrieved. "
    "Do not answer from general knowledge. Respond only with: "
    '"I could not find sufficient information in the retrieved document."'
)


class GenerationError(Exception):
    pass


_client: Client | None = None
_client_host: str | None = None


def _ollama_host() -> str:
    return getattr(settings, "OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_model() -> str:
    return settings.LLM_MODEL.strip()


def _ollama_client() -> Client:
    """Create/reuse the SDK client so every request uses the same host."""
    global _client, _client_host
    host = _ollama_host()
    if _client is None or _client_host != host:
        _client = Client(host=host, timeout=settings.OLLAMA_TIMEOUT)
        _client_host = host
    return _client


def _friendly_ollama_error(exc: Exception) -> GenerationError:
    msg = str(exc)
    model = _ollama_model()
    host = _ollama_host()
    lowered = msg.lower()

    if "unauthorized" in lowered or "authentication" in lowered or "sign in" in lowered:
        return GenerationError(
            "Ollama authentication failed. Run `ollama signin` and make sure "
            f"the signed-in account can access `{model}`."
        )
    if "not found" in lowered or "pull" in lowered:
        return GenerationError(
            f"Ollama could not find model `{model}`. Run `ollama pull {model}` "
            "and retry."
        )
    if "connection" in lowered or "connect" in lowered or "refused" in lowered:
        return GenerationError(
            f"Could not connect to Ollama at {host}. Make sure Ollama is running."
        )
    return GenerationError(f"Ollama model request failed: {msg}")


def _clean_model_output(text: str) -> str:
    if not text:
        return ""
    text = text.strip()

    final_match = re.search(r"<final>\s*(.*?)\s*</final>", text, flags=re.DOTALL | re.IGNORECASE)
    if final_match:
        return final_match.group(1).strip()

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</think>", "", text, flags=re.IGNORECASE).strip()

    for pattern in (r"(?is)\bfinal answer\s*:\s*(.+)$", r"(?is)\banswer\s*:\s*(.+)$"):
        match = re.search(pattern, text)
        if match and match.group(1).strip():
            text = match.group(1).strip()
            break

    prefixes = [
        r"^\s*Thinking\.\.\.",
        r"^\s*Let me analyze.*?(?:\n\n|\Z)",
        r"^\s*Let me carefully analyze.*?(?:\n\n|\Z)",
        r"^\s*Let's analyze.*?(?:\n\n|\Z)",
        r"^\s*I need to analyze.*?(?:\n\n|\Z)",
        r"^\s*First, I need to.*?(?:\n\n|\Z)",
        r"^\s*Looking at the context.*?(?:\n\n|\Z)",
    ]
    for pattern in prefixes:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    lines = []
    reasoning_starts = (
        "let me ", "first, ", "looking at ", "i need to ", "i should ",
        "i must ", "the question asks", "the user is asking", "i'll ",
        "i will ", "however, ", "wait, ", "so the answer should",
        "let me check", "i need to check", "i should check", "the context ",
        "i recall ", "this seems ",
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        lower = stripped.lower()
        if lower.startswith(reasoning_starts):
            continue
        if re.match(r"^\d+\.\s+(let me|i need|i should|looking|first|the question)", lower):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n\s*(Let me|I need to|I should|Looking at|The question asks).*?$", "", text, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(No sufficiently relevant passages were retrieved for this question.)"
    parts = []
    for c in chunks:
        page_label = f"Page {c.page_start}" if c.page_start == c.page_end else f"Pages {c.page_start}-{c.page_end}"
        section = f" | Section: {c.section_title}" if c.section_title else ""
        parts.append(f"[{page_label}{section}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def _format_history(history: list[Message], question: str = "") -> str:
    user_messages = [m for m in history if m.role == "user"]
    trimmed = user_messages[-max(1, settings.MAX_HISTORY_MESSAGES // 2):]
    prior = [m.content.strip() for m in trimmed if m.content.strip() and m.content.strip() != question.strip()]
    if not prior:
        return ""
    return "Previous user context (for resolving follow-up references only; not factual evidence):\n" + "\n".join(f"- {item}" for item in prior)


def build_messages(question: str, chunks: list[RetrievedChunk], history: list[Message]) -> list[dict]:
    plan = classify_query(question)
    context_block = _format_context(chunks)
    format_instruction = (
        "OUTPUT FORMAT: TABLE. The user is asking for structured information. Return a valid Markdown table with consistent columns; do not output a code block containing the table."
        if plan.output_format == "table"
        else "OUTPUT FORMAT: SIMPLE. Answer directly in normal prose unless a short list is genuinely required."
        if plan.output_format == "simple"
        else "OUTPUT FORMAT: LIST. Use a concise numbered or bulleted list."
    )
    user_turn = (
        "AUTHORITATIVE DOCUMENT EVIDENCE (use this as the only factual source):\n\n"
        f"{context_block}\n\n"
        f"User question: {question}\n\n"
        f"{format_instruction}\n\n"
        "Give a complete answer supported by the document evidence. For list/document/requirements questions, include every relevant numbered item and all subordinate notes, conditions, exceptions, dates, validity rules, and authority requirements in the retrieved section. Do not summarize away a requirement. "
        "For a person/title/message question, identify the person and summarize the message point-by-point when the evidence contains it. "
        "Do not rely on previous assistant answers if they conflict with the evidence. If the evidence contains an exact matching heading, named person, title, or section, treat it as decisive. "
        "Never claim information is absent when it is explicitly present. Match depth to the question. Do not explain reasoning."
    )
    if not chunks:
        user_turn += NO_EVIDENCE_NOTE
    history_context = _format_history(history, question)
    if history_context:
        user_turn = history_context + "\n\n" + user_turn
    return [{"role": "user", "content": user_turn}]


def _chat(messages: list[dict], stream: bool):
    try:
        response = _ollama_client().chat(
            model=_ollama_model(),
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            stream=stream,
            think=False,
            options={
                "num_predict": settings.LLM_MAX_TOKENS,
                "temperature": 0.0,
                "top_p": 0.8,
            },
        )
        return response
    except (OllamaResponseError, Exception) as exc:
        # Ollama's SDK raises ResponseError for HTTP/API errors and ordinary
        # exceptions for connection/timeouts. Convert both to a useful UI error.
        raise _friendly_ollama_error(exc) from exc



def _table_rows(text: str) -> list[list[str]]:
    """Extract pipe-table rows from model output without executing any HTML."""
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|") or "|" not in line[1:]:
            continue
        body = line.strip("|")
        cells = [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", body)]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def _is_table_separator(row: list[str]) -> bool:
    return bool(row) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in row)


def _valid_markdown_table(text: str) -> bool:
    rows = _table_rows(text)
    if len(rows) < 2 or not _is_table_separator(rows[1]):
        return False
    width = len(rows[0])
    if width < 2:
        return False
    return all(len(row) == width for row in rows[1:])



def _direct_extract_full_message(question: str, chunks: list[RetrievedChunk]) -> str:
    """Return a complete indexed message verbatim for explicit full-message requests.

    This deliberately bypasses LLM summarization: if the user asks for the full
    message, the safest/highest-accuracy behavior is to extract the dedicated
    message evidence block and return it unchanged.
    """
    q = question.lower()
    role = "director" if "director" in q else "principal" if "principal" in q else "vice chancellor" if "vice chancellor" in q or "vice-chancellor" in q else None
    if not role:
        return ""
    target_id = {
        "director": "message_director_full",
        "principal": "message_principal_full",
        "vice chancellor": "message_vice_chancellor_full",
    }[role]
    target = next((c for c in chunks if c.chunk_id == target_id or c.content_type == "message" and role in (c.section_title or "").lower()), None)
    if not target or not target.text.strip():
        return ""
    text = target.text.strip()
    # The dedicated block includes the signature and University of Delhi.
    # Add a concise identification line without altering the message itself.
    sig_match = re.search(r"(Prof\.?\s+[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,3})\s+" + re.escape(role), text, re.IGNORECASE)
    if sig_match:
        name = re.sub(r"\s+", " ", sig_match.group(1)).strip()
        label = {"director": "Director", "principal": "Principal", "vice chancellor": "Vice-Chancellor"}[role]
        return f"**{label}: {name}**\n\n**{label}'s Message:**\n\n{text}"
    return text


def _needs_answer_repair(answer: str, chunks: list[RetrievedChunk], question: str = "") -> bool:
    if not chunks:
        return False
    lowered = answer.strip().lower()
    absence_patterns = (
        "i could not find sufficient information", "no information", "not present in the document",
        "does not contain", "doesn't contain", "not included in the document",
        "is not included in the document", "cannot identify", "can't identify",
        "i don't see", "i do not see", "not identified in the document", "not mentioned in the document",
    )
    no_info = any(pattern in lowered for pattern in absence_patterns)
    plan = classify_query(question) if question else None
    invalid_table = bool(plan and plan.output_format == "table" and not _valid_markdown_table(answer))
    evidence_chars = sum(len(c.text) for c in chunks[:4])
    suspiciously_short = evidence_chars >= 800 and len(answer.strip()) < 220
    top = chunks[0]
    missing_signature = False
    if top.score >= 0.60:
        # Use Unicode-aware name matching without the accidental backspace
        # character that existed in the previous regex.
        names = re.findall(r"\b(?:Prof\.?|Dr\.?)\s+[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,3}", top.text)
        for name in names[:4]:
            if len(re.sub(r"\s+", " ", name).strip()) >= 7 and re.sub(r"\s+", " ", name).strip().lower() not in lowered:
                missing_signature = True
                break
    return no_info or suspiciously_short or missing_signature or invalid_table


def _repair_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    repair_prompt = (
        "The previous answer was incomplete or incorrectly claimed that the document contained no information. "
        "Ignore it and answer again using ONLY the authoritative document evidence below.\n\n"
        f"{_format_context(chunks)}\n\nQuestion: {question}\n\n"
        "Give the complete answer supported by this evidence. For document/requirements questions, reproduce every relevant numbered item and all subordinate notes, conditions, exceptions, dates, validity rules, and issuing-authority requirements belonging to the section. Do not summarize away a requirement. Do not say information is missing when it is present. "
        f"The required output format is {classify_query(question).output_format.upper()}. "
        "If the format is TABLE, return a valid Markdown table with a header, separator row, and identical column count on every row. "
        "Keep cells on one line and do not use HTML. Return only the final answer inside <final> and </final>."
    )
    response = _chat([{"role": "user", "content": repair_prompt}], stream=False)
    return _clean_model_output(response.message.content if response.message else "")


async def stream_answer(question: str, chunks: list[RetrievedChunk], history: list[Message]) -> AsyncIterator[str]:
    plan = classify_query(question)
    if plan.direct_extract:
        extracted = _direct_extract_full_message(question, chunks)
        if extracted:
            yield extracted
            return
    messages = build_messages(question, chunks, history)
    try:
        response = _chat(messages, stream=True)
        collected = []
        for part in response:
            content = getattr(getattr(part, "message", None), "content", "") or ""
            if content:
                collected.append(content)
        cleaned = _clean_model_output("".join(collected))
        if _needs_answer_repair(cleaned, chunks, question):
            repaired = _repair_answer(question, chunks)
            if repaired:
                cleaned = repaired
        if cleaned:
            yield cleaned
    except GenerationError:
        raise
    except Exception as exc:
        raise _friendly_ollama_error(exc) from exc


def generate_answer_sync(question: str, chunks: list[RetrievedChunk], history: list[Message]) -> str:
    plan = classify_query(question)
    if plan.direct_extract:
        extracted = _direct_extract_full_message(question, chunks)
        if extracted:
            return extracted
    messages = build_messages(question, chunks, history)
    response = _chat(messages, stream=False)
    answer = getattr(getattr(response, "message", None), "content", "") or ""
    cleaned = _clean_model_output(answer)
    if _needs_answer_repair(cleaned, chunks, question):
        repaired = _repair_answer(question, chunks)
        if repaired:
            cleaned = repaired
    return cleaned
