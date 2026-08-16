"""Ranking metrics. Pure Python so the harness pulls in no extra dependency."""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine of the angle between two vectors, in [-1, 1].

    Raises on a width mismatch rather than truncating, because silently comparing
    the first N dimensions of differently sized vectors is how a dimension change
    turns into quietly wrong scores instead of a visible failure.
    """
    if len(a) != len(b):
        raise ValueError(f"vector width mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Collection[str]) -> float:
    """1/rank of the first relevant hit, or 0.0 if none was retrieved."""
    for position, identifier in enumerate(ranked_ids, start=1):
        if identifier in relevant_ids:
            return 1.0 / position
    return 0.0


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> float:
    """1.0 when any relevant item appears in the top k, else 0.0."""
    return 1.0 if any(i in relevant_ids for i in ranked_ids[:k]) else 0.0


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
