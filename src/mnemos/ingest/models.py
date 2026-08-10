"""Normalized conversation models shared by parsers and the archive."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime | None = None
    ordinal: int


class Conversation(BaseModel):
    id: str
    provider: str
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source_path: str | None = None
    messages: list[Message] = Field(default_factory=list)
