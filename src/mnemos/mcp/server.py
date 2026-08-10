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
from neo4j import AsyncGraphDatabase

from mnemos.archive import store
from mnemos.config import Settings, get_settings

log = logging.getLogger(__name__)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool: asyncpg.Pool | None = None
        self.neo4j_driver: Any = None

    async def startup(self) -> None:
        self.pool = await store.connect(self.settings.postgres_dsn)
        await store.ensure_schema(self.pool)
        self.neo4j_driver = AsyncGraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    async def shutdown(self) -> None:
        if self.pool is not None:
            await self.pool.close()
        if self.neo4j_driver is not None:
            await self.neo4j_driver.close()


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
        """Search temporal memory (Neo4j entities/facts) and fall back to transcript text."""
        limit = max(1, min(limit, 25))
        hits: list[dict[str, Any]] = []

        assert state.neo4j_driver is not None
        cypher = """
        CALL db.index.fulltext.queryNodes('node_name_and_summary', $q) YIELD node, score
        RETURN coalesce(node.name, node.uuid) AS name,
               coalesce(node.summary, node.content, '') AS summary,
               labels(node) AS labels,
               score
        ORDER BY score DESC
        LIMIT $limit
        """
        try:
            async with state.neo4j_driver.session() as session:
                result = await session.run(cypher, q=query, limit=limit)
                records = [record.data() async for record in result]
                for rec in records:
                    hits.append(
                        {
                            "source": "neo4j",
                            "name": rec.get("name"),
                            "summary": rec.get("summary"),
                            "labels": rec.get("labels"),
                            "score": rec.get("score"),
                        }
                    )
        except Exception as exc:
            # Fulltext index may not exist yet on a fresh Neo4j.
            log.warning("Neo4j fulltext search unavailable: %s", exc)
            fallback = """
            MATCH (n)
            WHERE (n:Entity OR n:Episodic)
              AND (
                toLower(coalesce(n.name, '')) CONTAINS toLower($q)
                OR toLower(coalesce(n.summary, '')) CONTAINS toLower($q)
                OR toLower(coalesce(n.content, '')) CONTAINS toLower($q)
              )
            RETURN coalesce(n.name, n.uuid) AS name,
                   coalesce(n.summary, n.content, '') AS summary,
                   labels(n) AS labels,
                   1.0 AS score
            LIMIT $limit
            """
            try:
                async with state.neo4j_driver.session() as session:
                    result = await session.run(fallback, q=query, limit=limit)
                    records = [record.data() async for record in result]
                    for rec in records:
                        hits.append(
                            {
                                "source": "neo4j",
                                "name": rec.get("name"),
                                "summary": rec.get("summary"),
                                "labels": rec.get("labels"),
                                "score": rec.get("score"),
                            }
                        )
            except Exception as exc2:
                log.warning("Neo4j fallback search failed: %s", exc2)

        assert state.pool is not None
        if len(hits) < limit:
            pg_hits = await store.search_messages(state.pool, query, limit=limit - len(hits))
            for row in pg_hits:
                hits.append(
                    {
                        "source": "postgres",
                        "message_id": row["id"],
                        "conversation_id": row["conversation_id"],
                        "conversation_title": row["conversation_title"],
                        "role": row["role"],
                        "content": row["content"][:500],
                    }
                )

        return json.dumps({"query": query, "results": hits}, default=str, indent=2)

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
