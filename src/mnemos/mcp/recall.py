"""Recall: Graphiti hybrid search first, Postgres verbatim to fill remaining slots.

Graphiti's ``search_`` is the path that actually uses the embedder and the reranker.
The MCP tool used to query Neo4j fulltext directly, which made both of those components
dead on the read path.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from graphiti_core.search.search_config import SearchConfig, SearchResults
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_CROSS_ENCODER

log = logging.getLogger(__name__)

# Facts, then entities, then the raw episode the fact came from. Communities are skipped:
# the MVP never builds them, and each extra layer is another GPU round-trip on recall.
_RECALL_RECIPE = COMBINED_HYBRID_SEARCH_CROSS_ENCODER.model_copy(deep=True)
_RECALL_RECIPE.community_config = None


class GraphSearchClient(Protocol):
    async def search_(self, query: str, config: SearchConfig) -> SearchResults: ...


class MessageArchive(Protocol):
    async def search_messages(self, query: str, limit: int) -> list[dict[str, Any]]: ...


def recall_search_config(limit: int) -> SearchConfig:
    config = _RECALL_RECIPE.model_copy(deep=True)
    config.limit = limit
    return config


def flatten_search(results: SearchResults, limit: int) -> list[dict[str, Any]]:
    """Turn Graphiti's layered result into a single ranked list for the MCP tool.

    Edges (facts) come first: that is the memory. Nodes and episodes fill in names and
    the original conversation chunk. Truncation happens after merging so a query that
    only hits entities still returns them.
    """
    hits: list[dict[str, Any]] = []
    hits.extend(_facts(results))
    hits.extend(_entities(results))
    hits.extend(_episodes(results))
    return hits[:limit]


def _zip_scores(items: list[Any], scores: list[float]) -> list[tuple[Any, float | None]]:
    padded: list[float | None] = list(scores) + [None] * max(0, len(items) - len(scores))
    return list(zip(items, padded[: len(items)], strict=True))


def _facts(results: SearchResults) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for edge, score in _zip_scores(results.edges, results.edge_reranker_scores):
        hits.append(
            {
                "source": "graphiti",
                "kind": "fact",
                "uuid": edge.uuid,
                "name": edge.name,
                "text": edge.fact,
                "conversation_id": edge.group_id,
                "score": score,
            }
        )
    return hits


def _entities(results: SearchResults) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for node, score in _zip_scores(results.nodes, results.node_reranker_scores):
        hits.append(
            {
                "source": "graphiti",
                "kind": "entity",
                "uuid": node.uuid,
                "name": node.name,
                "text": node.summary,
                "conversation_id": node.group_id,
                "labels": node.labels,
                "score": score,
            }
        )
    return hits


def _episodes(results: SearchResults) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for episode, score in _zip_scores(results.episodes, results.episode_reranker_scores):
        hits.append(
            {
                "source": "graphiti",
                "kind": "episode",
                "uuid": episode.uuid,
                "name": episode.name,
                "text": episode.content[:800],
                "conversation_id": episode.group_id,
                "score": score,
            }
        )
    return hits


def _postgres_hits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": "postgres",
            "kind": "message",
            "message_id": row["id"],
            "conversation_id": row["conversation_id"],
            "conversation_title": row["conversation_title"],
            "role": row["role"],
            "text": row["content"][:500],
        }
        for row in rows
    ]


async def recall(
    query: str,
    limit: int,
    *,
    graphiti: GraphSearchClient | None,
    archive: MessageArchive | None,
) -> dict[str, Any]:
    """Search the graph, then pad with verbatim transcript matches if needed."""
    limit = max(1, min(limit, 25))
    hits: list[dict[str, Any]] = []

    if graphiti is not None:
        try:
            results = await graphiti.search_(query, recall_search_config(limit))
            hits = flatten_search(results, limit)
        except Exception:
            log.exception("Graphiti hybrid search failed")

    remaining = limit - len(hits)
    if remaining > 0 and archive is not None:
        try:
            rows = await archive.search_messages(query, remaining)
            hits.extend(_postgres_hits(rows))
        except Exception:
            log.exception("Postgres transcript search failed")

    return {"query": query, "results": hits}
