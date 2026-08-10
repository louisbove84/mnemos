"""Offline cross-encoder stand-in so Graphiti does not call OpenAI rerank APIs."""

from __future__ import annotations

from graphiti_core.cross_encoder.client import CrossEncoderClient


class LexicalReranker(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        tokens = {t for t in query.lower().split() if t}
        scored: list[tuple[str, float]] = []
        for passage in passages:
            words = passage.lower().split()
            if not words:
                scored.append((passage, 0.0))
                continue
            overlap = sum(1 for w in words if w in tokens)
            scored.append((passage, overlap / float(len(words))))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored
