"""
Repository functions: every piece of SQL in the application lives here so
that route handlers and services never write raw queries themselves. All
queries use parameter binding (never string interpolation) to avoid SQL
injection.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from app.database.db import get_db


# ---------------------------------------------------------------------------
# Data classes (lightweight view models, not an ORM)
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: int
    email: str
    username: str
    password_hash: str
    created_at: str


@dataclass
class Conversation:
    id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str


@dataclass
class SourceRef:
    id: int
    message_id: int
    page_number: int
    chunk_id: str
    section_title: Optional[str]
    excerpt: str
    relevance_score: float


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str
    sources: list[SourceRef] = field(default_factory=list)


def _row_to_user(row: sqlite3.Row) -> User:
    return User(row["id"], row["email"], row["username"], row["password_hash"], row["created_at"])


def _row_to_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(row["id"], row["user_id"], row["title"], row["created_at"], row["updated_at"])


def _row_to_source(row: sqlite3.Row) -> SourceRef:
    return SourceRef(
        row["id"], row["message_id"], row["page_number"], row["chunk_id"],
        row["section_title"], row["excerpt"], row["relevance_score"],
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    return Message(row["id"], row["conversation_id"], row["role"], row["content"], row["created_at"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(email: str, username: str, password_hash: str) -> User:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
            (email.lower().strip(), username.strip(), password_hash),
        )
        user_id = cur.lastrowid
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row)


def get_user_by_email(email: str) -> Optional[User]:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return _row_to_user(row) if row else None


def get_user_by_username(username: str) -> Optional[User]:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return _row_to_user(row) if row else None


def get_user_by_id(user_id: int) -> Optional[User]:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def create_conversation(user_id: int, title: str = "New conversation") -> Conversation:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)", (user_id, title)
        )
        row = db.execute("SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_conversation(row)


def list_conversations(user_id: int) -> list[Conversation]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_conversation(r) for r in rows]


def get_conversation(conversation_id: int, user_id: int) -> Optional[Conversation]:
    """Fetch a conversation, scoped to its owner. Returns None if it belongs
    to someone else, which is how we prevent cross-user access."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        return _row_to_conversation(row) if row else None


def rename_conversation(conversation_id: int, user_id: int, title: str) -> bool:
    with get_db() as db:
        cur = db.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (title.strip()[:120], conversation_id, user_id),
        )
        return cur.rowcount > 0


def touch_conversation(conversation_id: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Messages & sources
# ---------------------------------------------------------------------------

def add_message(conversation_id: int, role: str, content: str) -> Message:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        row = db.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_message(row)


def add_sources(message_id: int, sources: list[dict]) -> None:
    if not sources:
        return
    with get_db() as db:
        db.executemany(
            "INSERT INTO sources (message_id, page_number, chunk_id, section_title, "
            "excerpt, relevance_score) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    message_id,
                    s["page_number"],
                    s["chunk_id"],
                    s.get("section_title"),
                    s["excerpt"],
                    s["relevance_score"],
                )
                for s in sources
            ],
        )


def list_messages(conversation_id: int) -> list[Message]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        messages = [_row_to_message(r) for r in rows]
        if not messages:
            return messages
        ids = [m.id for m in messages]
        placeholders = ",".join("?" for _ in ids)
        src_rows = db.execute(
            f"SELECT * FROM sources WHERE message_id IN ({placeholders}) ORDER BY relevance_score DESC",
            ids,
        ).fetchall()
        by_message: dict[int, list[SourceRef]] = {}
        for r in src_rows:
            by_message.setdefault(r["message_id"], []).append(_row_to_source(r))
        for m in messages:
            m.sources = by_message.get(m.id, [])
        return messages
