"""Run Graphiti episode ingestion against the OpenAI-compatible llm Service."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType

from mnemos.archive.store import message_to_episode_text
from mnemos.config import Settings
from mnemos.extract.embedder import build_embedder
from mnemos.extract.reranker import build_reranker
from mnemos.ingest.models import Conversation

log = logging.getLogger(__name__)


async def build_graphiti(settings: Settings, *, build_indices: bool = True) -> Graphiti:
    # Keep Graphiti's internal dim in sync with the configured embedder.
    os.environ.setdefault("EMBEDDING_DIM", str(settings.embed_dim))

    llm_config = LLMConfig(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        small_model=settings.llm_model,
    )
    # 0.5B + small context cannot honor Graphiti's default 16k completion budget.
    llm_client = OpenAIClient(config=llm_config, max_tokens=512)
    graphiti = Graphiti(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password,
        llm_client=llm_client,
        embedder=build_embedder(settings),
        cross_encoder=build_reranker(settings),
    )
    # Ingest owns index creation. MCP is a reader and must not race that on startup.
    if build_indices:
        await graphiti.build_indices_and_constraints()
    return graphiti


async def extract_conversation(
    graphiti: Graphiti,
    conversation: Conversation,
) -> None:
    text = message_to_episode_text(conversation.messages, conversation.title)
    reference_time = conversation.updated_at or conversation.created_at or datetime.now(UTC)
    await graphiti.add_episode(
        name=conversation.title or conversation.id,
        episode_body=text,
        source=EpisodeType.message,
        source_description=f"{conversation.provider} export",
        reference_time=reference_time,
        group_id=conversation.id,
    )


async def extract_conversations(
    settings: Settings,
    conversations: list[Conversation],
) -> dict[str, Any]:
    if not settings.extract_enabled:
        return {"skipped": True, "count": 0}

    graphiti = await build_graphiti(settings)
    ok = 0
    errors: list[str] = []
    try:
        for conversation in conversations[: settings.max_episodes_per_run]:
            try:
                await extract_conversation(graphiti, conversation)
                ok += 1
            except Exception as exc:
                # Continue across episodes so one bad conversation does not abort the run.
                log.exception("Graphiti extraction failed for %s", conversation.id)
                errors.append(f"{conversation.id}: {exc}")
    finally:
        await graphiti.close()  # type: ignore[no-untyped-call]

    return {"skipped": False, "count": ok, "errors": errors}
