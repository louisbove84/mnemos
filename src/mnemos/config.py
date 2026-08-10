"""Runtime settings for ingest and MCP. All values come from the environment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MNEMOS_", extra="ignore")

    inbox_dir: str = "/data/inbox"
    processed_dir: str = "/data/processed"

    postgres_dsn: str = "postgresql://mnemos:mnemos@postgres:5432/mnemos"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mnemos"

    llm_base_url: str = "http://llm:8000/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "/models/qwen2.5-0.5b/qwen2.5-0.5b-instruct-q4_k_m.gguf"

    # Embeddings come from a local OpenAI-compatible server. "hash" swaps in the
    # deterministic stand-in, which has no semantics and is only for tests and
    # bring-up before the embed service exists.
    embedder: Literal["openai_compatible", "hash"] = "openai_compatible"
    embed_base_url: str = "http://embed:11434/v1"
    embed_api_key: str = "not-needed"
    embed_model: str = "nomic-embed-text"
    # Must match the model's output width and Graphiti's EMBEDDING_DIM. Changing
    # it invalidates every vector already written to Neo4j.
    embed_dim: int = 768

    extract_enabled: bool = True
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8080

    # Cap episodes per run so a huge export cannot wedge the 0.5B model for hours.
    max_episodes_per_run: int = Field(default=50, ge=1)


def get_settings() -> Settings:
    return Settings()
