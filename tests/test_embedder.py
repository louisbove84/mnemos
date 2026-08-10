"""Embedder selection, plus the offline Graphiti helpers it can fall back to."""

from __future__ import annotations

import pytest
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

from mnemos.config import Settings
from mnemos.extract.embedder import HashEmbedder, build_embedder
from mnemos.extract.reranker import LexicalReranker


@pytest.mark.asyncio
async def test_hash_embedder_dim_and_stability() -> None:
    embedder = HashEmbedder(dim=1024)
    a = await embedder.create("Cedar Ridge Loop")
    b = await embedder.create("Cedar Ridge Loop")
    c = await embedder.create("something else")
    assert len(a) == 1024
    assert a == b
    assert a != c


def test_build_embedder_targets_the_embed_service_by_default() -> None:
    settings = Settings(
        embed_base_url="http://embed:11434/v1",
        embed_model="nomic-embed-text",
        embed_dim=768,
    )
    embedder = build_embedder(settings)
    assert isinstance(embedder, OpenAIEmbedder)
    config = embedder.config
    assert isinstance(config, OpenAIEmbedderConfig)
    assert config.embedding_model == "nomic-embed-text"
    assert config.embedding_dim == 768
    assert config.base_url == "http://embed:11434/v1"


def test_build_embedder_hash_mode_needs_no_service() -> None:
    embedder = build_embedder(Settings(embedder="hash", embed_dim=64))
    assert isinstance(embedder, HashEmbedder)
    assert embedder.dim == 64


@pytest.mark.asyncio
async def test_lexical_reranker_orders_by_overlap() -> None:
    reranker = LexicalReranker()
    ranked = await reranker.rank(
        "dog Nimbus",
        ["weather report", "Nimbus the dog on Cedar Ridge", "unrelated"],
    )
    assert ranked[0][0].startswith("Nimbus")
