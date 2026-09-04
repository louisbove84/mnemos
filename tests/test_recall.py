"""Recall path tests. Graphiti and Postgres are stubbed — no cluster required."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.search.search_config import SearchConfig, SearchResults

from mnemos.mcp.recall import flatten_search, recall, recall_search_config


def _now() -> datetime:
    return datetime.now(UTC)


def _edge(fact: str, *, group_id: str = "conv-hike") -> EntityEdge:
    return EntityEdge(
        group_id=group_id,
        source_node_uuid="src",
        target_node_uuid="dst",
        created_at=_now(),
        name="PARTICIPATED_IN",
        fact=fact,
    )


def _entity(name: str, summary: str) -> EntityNode:
    return EntityNode(name=name, group_id="conv-hike", summary=summary, labels=["Entity"])


def _episode(name: str, content: str) -> EpisodicNode:
    return EpisodicNode(
        name=name,
        group_id="conv-hike",
        source=EpisodeType.message,
        source_description="chatgpt export",
        content=content,
        valid_at=_now(),
    )


class _FakeGraphiti:
    def __init__(self, results: SearchResults | Exception) -> None:
        self._results = results
        self.calls: list[tuple[str, SearchConfig]] = []

    async def search_(self, query: str, config: SearchConfig) -> SearchResults:
        self.calls.append((query, config))
        if isinstance(self._results, Exception):
            raise self._results
        return self._results


class _FakeArchive:
    def __init__(self, rows: list[dict[str, Any]] | Exception) -> None:
        self._rows = rows

    async def search_messages(self, query: str, limit: int) -> list[dict[str, Any]]:
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows[:limit]


def test_recall_search_config_skips_communities_and_honors_limit() -> None:
    config = recall_search_config(5)
    assert config.limit == 5
    assert config.community_config is None
    assert config.edge_config is not None
    assert config.node_config is not None
    assert config.episode_config is not None
    assert config.edge_config.reranker.value == "cross_encoder"


def test_flatten_search_puts_facts_ahead_of_entities() -> None:
    results = SearchResults(
        edges=[_edge("Nimbus hiked Cedar Ridge")],
        edge_reranker_scores=[0.91],
        nodes=[_entity("Nimbus", "the dog on the hike")],
        node_reranker_scores=[0.4],
        episodes=[_episode("aurora", "We set off before dawn.")],
        episode_reranker_scores=[0.2],
    )
    hits = flatten_search(results, limit=8)
    assert [h["kind"] for h in hits] == ["fact", "entity", "episode"]
    assert hits[0]["text"] == "Nimbus hiked Cedar Ridge"
    assert hits[0]["conversation_id"] == "conv-hike"
    assert hits[0]["score"] == pytest.approx(0.91)
    assert hits[1]["name"] == "Nimbus"


def test_flatten_search_truncates_after_merging_layers() -> None:
    results = SearchResults(
        edges=[_edge("fact one"), _edge("fact two")],
        nodes=[_entity("Nimbus", "the dog")],
    )
    hits = flatten_search(results, limit=2)
    assert [h["kind"] for h in hits] == ["fact", "fact"]


@pytest.mark.asyncio
async def test_recall_uses_graphiti_and_does_not_pad_when_full() -> None:
    graphiti = _FakeGraphiti(
        SearchResults(
            edges=[_edge(f"fact {i}") for i in range(8)],
            edge_reranker_scores=[1.0] * 8,
        )
    )
    archive = _FakeArchive(
        [
            {
                "id": "m1",
                "conversation_id": "c",
                "conversation_title": "t",
                "role": "user",
                "content": "x",
            }
        ]
    )
    payload = await recall(
        "how did the puppy handle the walk", 8, graphiti=graphiti, archive=archive
    )
    assert len(payload["results"]) == 8
    assert all(h["source"] == "graphiti" for h in payload["results"])
    assert graphiti.calls[0][0] == "how did the puppy handle the walk"
    assert graphiti.calls[0][1].limit == 8


@pytest.mark.asyncio
async def test_recall_pads_with_postgres_when_the_graph_is_thin() -> None:
    graphiti = _FakeGraphiti(SearchResults(edges=[_edge("Nimbus hiked")]))
    archive = _FakeArchive(
        [
            {
                "id": "msg-1",
                "conversation_id": "conv-hike",
                "conversation_title": "Cedar Ridge",
                "role": "user",
                "content": "Nimbus came along",
            }
        ]
    )
    payload = await recall("the dog", 8, graphiti=graphiti, archive=archive)
    assert payload["results"][0]["source"] == "graphiti"
    assert payload["results"][1]["source"] == "postgres"
    assert payload["results"][1]["kind"] == "message"
    assert payload["results"][1]["message_id"] == "msg-1"


@pytest.mark.asyncio
async def test_recall_falls_back_to_postgres_when_graphiti_raises() -> None:
    graphiti = _FakeGraphiti(RuntimeError("neo4j is down"))
    archive = _FakeArchive(
        [
            {
                "id": "msg-1",
                "conversation_id": "conv-hike",
                "conversation_title": "Cedar Ridge",
                "role": "assistant",
                "content": "Nimbus trotted the loop",
            }
        ]
    )
    payload = await recall("Nimbus", 8, graphiti=graphiti, archive=archive)
    assert [h["source"] for h in payload["results"]] == ["postgres"]


@pytest.mark.asyncio
async def test_recall_works_with_neither_backend() -> None:
    payload = await recall("anything", 8, graphiti=None, archive=None)
    assert payload["results"] == []
    assert payload["query"] == "anything"


@pytest.mark.asyncio
async def test_recall_clamps_limit() -> None:
    graphiti = _FakeGraphiti(SearchResults())
    await recall("q", 0, graphiti=graphiti, archive=None)
    assert graphiti.calls[0][1].limit == 1
    await recall("q", 99, graphiti=graphiti, archive=None)
    assert graphiti.calls[1][1].limit == 25
