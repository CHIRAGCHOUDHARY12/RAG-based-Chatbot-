from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth.routes import get_current_user
from app.chat.schemas import AskRequest, NewConversationRequest, RenameConversationRequest
from app.chat.service import ChatServiceError, ask_stream
from app.database import repositories as repo

logger = logging.getLogger("chat.routes")
router = APIRouter(prefix="/api")


def _unauthorized() -> JSONResponse:
    return JSONResponse({"error": "Authentication required."}, status_code=401)


@router.get("/conversations")
async def api_list_conversations(request: Request):
    user = get_current_user(request)
    if not user:
        return _unauthorized()
    conversations = repo.list_conversations(user.id)
    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in conversations
        ]
    }


@router.post("/conversations")
async def api_create_conversation(request: Request, body: NewConversationRequest):
    user = get_current_user(request)
    if not user:
        return _unauthorized()
    conversation = repo.create_conversation(user.id, body.title)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@router.get("/conversations/{conversation_id}/messages")
async def api_get_messages(request: Request, conversation_id: int):
    user = get_current_user(request)
    if not user:
        return _unauthorized()
    conversation = repo.get_conversation(conversation_id, user.id)
    if not conversation:
        return JSONResponse({"error": "Conversation not found."}, status_code=404)
    messages = repo.list_messages(conversation_id)
    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "sources": [
                    {
                        "page_start": s.page_number,
                        "page_end": s.page_number,
                        "section_title": s.section_title,
                        "excerpt": s.excerpt,
                        "score": s.relevance_score,
                    }
                    for s in m.sources
                ],
            }
            for m in messages
        ]
    }


@router.patch("/conversations/{conversation_id}")
async def api_rename_conversation(request: Request, conversation_id: int, body: RenameConversationRequest):
    user = get_current_user(request)
    if not user:
        return _unauthorized()
    ok = repo.rename_conversation(conversation_id, user.id, body.title)
    if not ok:
        return JSONResponse({"error": "Conversation not found."}, status_code=404)
    return {"ok": True}


@router.delete("/conversations/{conversation_id}")
async def api_delete_conversation(request: Request, conversation_id: int):
    user = get_current_user(request)
    if not user:
        return _unauthorized()
    ok = repo.delete_conversation(conversation_id, user.id)
    if not ok:
        return JSONResponse({"error": "Conversation not found."}, status_code=404)
    return {"ok": True}


@router.post("/chat/ask")
async def api_ask(request: Request, body: AskRequest):
    user = get_current_user(request)
    if not user:
        return _unauthorized()

    vector_store = request.app.state.vector_store
    index_status = request.app.state.index_status
    if not index_status.ready:
        return JSONResponse(
            {"error": f"The knowledge base is not ready: {index_status.message}"},
            status_code=503,
        )

    async def event_stream():
        try:
            async for fragment in ask_stream(body.conversation_id, user.id, body.question, vector_store):
                yield f"data: {json.dumps({'delta': fragment})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except ChatServiceError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        except Exception as exc:  # last-resort guard: never leak a raw traceback to the client
            logger.exception("Unexpected error while answering question")
            yield f"data: {json.dumps({'error': 'Something went wrong while answering. Please try again.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
