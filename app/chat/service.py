from __future__ import annotations

from collections.abc import AsyncIterator

from app.database import repositories as repo
from app.rag.generator import GenerationError, stream_answer
from app.rag.retriever import RetrievedChunk, retrieve
from app.rag.query_router import classify_query
from app.rag.vector_store import VectorStore


class ChatServiceError(Exception):
    """User-facing error raised by the chat service."""

    pass


async def ask_stream(
    conversation_id: int,
    user_id: int,
    question: str,
    vector_store: VectorStore,
) -> AsyncIterator[str]:
    """
    Retrieve relevant document context and stream an answer from the LLM.

    The conversation is scoped to the authenticated user so that a user
    cannot access another user's conversation.
    """

    # ------------------------------------------------------------------
    # 1. Verify that the conversation exists and belongs to this user.
    # ------------------------------------------------------------------
    conversation = repo.get_conversation(conversation_id, user_id)

    if not conversation:
        raise ChatServiceError("Conversation not found.")

    # ------------------------------------------------------------------
    # 2. Get previous conversation history BEFORE adding the new question.
    # ------------------------------------------------------------------
    history = repo.list_messages(conversation_id)

    # ------------------------------------------------------------------
    # 3. Store the user's message.
    # ------------------------------------------------------------------
    try:
        repo.add_message(
            conversation_id=conversation_id,
            role="user",
            content=question,
        )
    except Exception as exc:
        raise ChatServiceError(
            "Could not save your message. Please try again."
        ) from exc

    # ------------------------------------------------------------------
    # 4. Retrieve relevant chunks from the document.
    # ------------------------------------------------------------------
    try:
        plan = classify_query(question)
        chunks: list[RetrievedChunk] = retrieve(
            query=question,
            store=vector_store,
            top_k=plan.max_context,
        )
    except Exception as exc:
        raise ChatServiceError(
            f"Document retrieval failed: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 5. Generate and stream the answer.
    # ------------------------------------------------------------------
    answer_parts: list[str] = []

    try:
        async for fragment in stream_answer(
            question=question,
            chunks=chunks,
            history=history,
        ):
            answer_parts.append(fragment)
            yield fragment

    except GenerationError as exc:
        raise ChatServiceError(str(exc)) from exc
    except Exception as exc:
        raise ChatServiceError(
            f"Unable to generate an answer: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 6. Persist the completed assistant response and its sources.
    # ------------------------------------------------------------------
    answer = "".join(answer_parts).strip()

    if not answer:
        raise ChatServiceError(
            "The language model returned an empty response."
        )

    try:
        assistant_message = repo.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
        )

        source_records = [
            {
                "page_number": chunk.page_start,
                "chunk_id": chunk.chunk_id,
                "section_title": chunk.section_title,
                "excerpt": chunk.text,
                "relevance_score": chunk.score,
            }
            for chunk in chunks
        ]

        repo.add_sources(
            message_id=assistant_message.id,
            sources=source_records,
        )

        repo.touch_conversation(conversation_id)

    except Exception as exc:
        raise ChatServiceError(
            "The answer was generated, but it could not be saved. "
            "Please try again."
        ) from exc
