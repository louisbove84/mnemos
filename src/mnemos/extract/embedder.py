"""Embedder selection for Graphiti: a local embeddings service, or an offline stand-in."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Iterable

from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

from mnemos.config import Settings


def _hash_to_vec(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    buf = digest
    # Need 4 bytes per dimension as unsigned ints, then map into [-1, 1].
    while len(buf) < dim * 4:
        buf += hashlib.sha256(buf).digest()
    values: list[float] = []
    for i in range(dim):
        (raw,) = struct.unpack_from(">I", buf, i * 4)
        values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class HashEmbedder(EmbedderClient):
    """Offline stand-in for a real embedding model.

    Vectors are stable per input but carry no semantics, so nearest-neighbour search
    over them is meaningless. Only for tests and bring-up before embed is reachable.
    """

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        if isinstance(input_data, str):
            return _hash_to_vec(input_data, self.dim)
        if isinstance(input_data, list) and input_data and isinstance(input_data[0], str):
            vecs = [_hash_to_vec(str(s), self.dim) for s in input_data]
            acc = [0.0] * self.dim
            for v in vecs:
                for i, x in enumerate(v):
                    acc[i] += x
            n = float(len(vecs)) or 1.0
            mean = [x / n for x in acc]
            norm = math.sqrt(sum(v * v for v in mean)) or 1.0
            return [v / norm for v in mean]
        return _hash_to_vec(str(list(input_data)), self.dim)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [_hash_to_vec(text, self.dim) for text in input_data_list]


def build_embedder(settings: Settings) -> EmbedderClient:
    """Pick the embedder named by settings.embedder.

    The default target is the in-cluster embed Service (Ollama), which serves the
    OpenAI /v1/embeddings contract, so the same client works against any provider
    that speaks it.
    """
    if settings.embedder == "hash":
        return HashEmbedder(dim=settings.embed_dim)
    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=settings.embed_api_key,
            embedding_model=settings.embed_model,
            embedding_dim=settings.embed_dim,
            base_url=settings.embed_base_url,
        )
    )
