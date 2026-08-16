"""Minimal MCP tools: memory search/recall and verbatim message fetch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from mcp.server.fastmcp import FastMCP

from mnemos.archive import store
from mnemos.config import Settings, get_settings
from mnemos.extract.graphiti_pipeline import build_graphiti
from mnemos.mcp.recall import recall

log = logging.getLogger(__name__)


class _PoolArchive:
    """Adapts an asyncpg pool to the MessageArchive protocol used by recall."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def search_messages(self, query: str, limit: int) -> list[dict[str, Any]]:
        return await store.search_messages(self._pool, query, limit=limit)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool: asyncpg.Pool | None = None
        self.graphiti: Any = None

    async def startup(self) -> None:
        self.pool = await store.connect(self.settings.postgres_dsn)
        await store.ensure_schema(self.pool)
        try:
            self.graphiti = await build_graphiti(self.settings, build_indices=False)
        except Exception:
            # Stay up on Postgres alone so fetch_verbatim and search_transcripts still work
            # while Neo4j or embed is coming up.
            log.exception("Graphiti client failed to start; recall will use Postgres only")
            self.graphiti = None

    async def shutdown(self) -> None:
        if self.graphiti is not None:
            await self.graphiti.close()
            self.graphiti = None
        if self.pool is not None:
            await self.pool.close()


def create_mcp(settings: Settings | None = None) -> FastMCP[Any]:
    settings = settings or get_settings()
    state = AppState(settings)

    @asynccontextmanager
    async def lifespan(_server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
        await state.startup()
        try:
            yield {"state": state}
        finally:
            await state.shutdown()

    mcp = FastMCP(
        "mnemos",
        host=settings.mcp_host,
        port=settings.mcp_port,
        lifespan=lifespan,
    )

    @mcp.tool()
    async def recall_memory(query: str, limit: int = 8) -> str:
        """Search temporal memory (facts, entities, episodes) and fall back to transcript text."""
        assert state.pool is not None
        payload = await recall(
            query,
            limit,
            graphiti=state.graphiti,
            archive=_PoolArchive(state.pool),
        )
        return json.dumps(payload, default=str, indent=2)

    @mcp.tool()
    async def fetch_verbatim(
        message_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> str:
        """Fetch verbatim transcript text by message id or conversation id."""
        assert state.pool is not None
        if message_id:
            row = await store.get_message(state.pool, message_id)
            if row is None:
                return json.dumps({"error": "message not found", "message_id": message_id})
            return json.dumps(row, default=str, indent=2)
        if conversation_id:
            rows = await store.get_conversation_excerpt(
                state.pool, conversation_id, limit=max(1, min(limit, 200))
            )
            return json.dumps(
                {"conversation_id": conversation_id, "messages": rows},
                default=str,
                indent=2,
            )
        return json.dumps({"error": "provide message_id or conversation_id"})

    @mcp.tool()
    async def search_transcripts(query: str, limit: int = 10) -> str:
        """Search Postgres for verbatim message text (ILIKE)."""
        assert state.pool is not None
        rows = await store.search_messages(state.pool, query, limit=max(1, min(limit, 50)))
        slim = [
            {
                "message_id": r["id"],
                "conversation_id": r["conversation_id"],
                "title": r["conversation_title"],
                "role": r["role"],
                "content": r["content"][:800],
            }
            for r in rows
        ]
        return json.dumps({"query": query, "results": slim}, indent=2)

    return mcp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    mcp = create_mcp(settings)
    asyncio.run(mcp.run_sse_async())


if __name__ == "__main__":
    main()
