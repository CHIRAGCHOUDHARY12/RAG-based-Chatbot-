from __future__ import annotations

from pydantic import BaseModel, Field


class NewConversationRequest(BaseModel):
    title: str = Field(default="New conversation", max_length=120)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AskRequest(BaseModel):
    conversation_id: int
    question: str = Field(min_length=1, max_length=2000)


class SourceOut(BaseModel):
    page_start: int
    page_end: int
    section_title: str | None
    excerpt: str
    score: float


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str
    sources: list[SourceOut] = []
