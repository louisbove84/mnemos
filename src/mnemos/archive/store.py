"""Async Postgres helpers for the verbatim archive."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import asyncpg

from mnemos.archive.schema import SCHEMA_SQL_BASE, TRIGRAM_INDEX_SQL
from mnemos.ingest.models import Conversation, Message


async def connect(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=4)


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL_BASE)
        # Extension unavailable in some images; text search still works via ILIKE.
        with suppress(asyncpg.PostgresError):
            await conn.execute(TRIGRAM_INDEX_SQL)


async def start_run(pool: asyncpg.Pool, source_path: str, provider: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ingest_runs (source_path, provider)
            VALUES ($1, $2)
            RETURNING id
            """,
            source_path,
            provider,
        )
        assert row is not None
        return int(row["id"])


async def finish_run(
    pool: asyncpg.Pool,
    run_id: int,
    *,
    conversation_count: int,
    message_count: int,
    status: str = "ok",
    error: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE ingest_runs
            SET finished_at = NOW(),
                conversation_count = $2,
                message_count = $3,
                status = $4,
                error = $5
            WHERE id = $1
            """,
            run_id,
            conversation_count,
            message_count,
            status,
            error,
        )


async def upsert_conversation(pool: asyncpg.Pool, conversation: Conversation) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO conversations (id, provider, title, created_at, updated_at, source_path)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = EXCLUDED.updated_at,
                source_path = EXCLUDED.source_path,
                ingested_at = NOW()
            """,
            conversation.id,
            conversation.provider,
            conversation.title,
            conversation.created_at,
            conversation.updated_at,
            conversation.source_path,
        )
        await conn.execute(
            "DELETE FROM messages WHERE conversation_id = $1",
            conversation.id,
        )
        await conn.executemany(
            """
            INSERT INTO messages (id, conversation_id, role, content, created_at, ordinal)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (
                    m.id,
                    m.conversation_id,
                    m.role,
                    m.content,
                    m.created_at,
                    m.ordinal,
                )
                for m in conversation.messages
            ],
        )


async def get_message(pool: asyncpg.Pool, message_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, m.ordinal,
                   c.title AS conversation_title, c.provider
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.id = $1
            """,
            message_id,
        )
        return dict(row) if row else None


async def get_conversation_excerpt(
    pool: asyncpg.Pool,
    conversation_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, conversation_id, role, content, created_at, ordinal
            FROM messages
            WHERE conversation_id = $1
            ORDER BY ordinal
            LIMIT $2
            """,
            conversation_id,
            limit,
        )
        return [dict(r) for r in rows]


async def search_messages(
    pool: asyncpg.Pool,
    query: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    pattern = f"%{query}%"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, m.ordinal,
                   c.title AS conversation_title, c.provider
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.content ILIKE $1
            ORDER BY m.created_at DESC NULLS LAST
            LIMIT $2
            """,
            pattern,
            limit,
        )
        return [dict(r) for r in rows]


def message_to_episode_text(messages: list[Message], title: str) -> str:
    lines = [f"Conversation: {title}"]
    for m in messages:
        lines.append(f"{m.role}: {m.content}")
    return "\n".join(lines)
