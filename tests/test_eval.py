"""Evaluation harness tests. Runs on the hash embedder so no service is needed."""

from __future__ import annotations

import pytest
from graphiti_core.cross_encoder.client import CrossEncoderClient

from mnemos.eval.dataset import PASSAGES, PHRASE_PAIRS, RETRIEVAL_CASES
from mnemos.eval.harness import evaluate, score_pairs
from mnemos.eval.metrics import cosine_similarity, mean, recall_at_k, reciprocal_rank
from mnemos.extract.embedder import HashEmbedder
from mnemos.extract.reranker import LexicalReranker


class _IdentityReranker(CrossEncoderClient):
    """Control for the harness: keeps the embedder's order, so delta must be zero."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        return [(passage, 1.0) for passage in passages]


def test_cosine_similarity_bounds() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_similarity_rejects_width_mismatch() -> None:
    # A dimension change must fail loudly rather than compare a truncated prefix.
    with pytest.raises(ValueError, match="width mismatch"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_reciprocal_rank_and_recall() -> None:
    ranked = ["a", "b", "c", "d"]
    assert reciprocal_rank(ranked, {"a"}) == pytest.approx(1.0)
    assert reciprocal_rank(ranked, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(ranked, {"z"}) == 0.0
    assert recall_at_k(ranked, {"c"}, 3) == 1.0
    assert recall_at_k(ranked, {"c"}, 2) == 0.0


def test_mean_handles_empty() -> None:
    assert mean([]) == 0.0
    assert mean([1.0, 2.0]) == pytest.approx(1.5)


def test_dataset_ids_are_unique_and_referenced() -> None:
    ids = [p.id for p in PASSAGES]
    assert len(ids) == len(set(ids))
    texts = [p.text for p in PASSAGES]
    # The reranker maps its output back to ids by text, which needs distinct texts.
    assert len(texts) == len(set(texts))
    for case in RETRIEVAL_CASES:
        assert case.relevant_ids
        assert set(case.relevant_ids) <= set(ids)


@pytest.mark.asyncio
async def test_score_pairs_covers_every_pair() -> None:
    report = await score_pairs(HashEmbedder(dim=64))
    assert len(report.results) == len(PHRASE_PAIRS)
    assert all(-1.0 <= r.score <= 1.0 for r in report.results)


@pytest.mark.asyncio
async def test_hash_embedder_shows_no_separation() -> None:
    """The baseline's whole point: stable vectors that encode no meaning.

    Guards the harness itself — if this ever reported strong separation for a hash,
    the metric would be measuring something other than semantic similarity.
    """
    report = await evaluate(HashEmbedder(dim=256), {"lexical": LexicalReranker()}, PASSAGES, "hash")
    assert report.dimension == 256
    assert abs(report.pairs.separation) < 0.2


@pytest.mark.asyncio
async def test_evaluate_scores_every_reranker_on_one_embedding_run() -> None:
    rerankers = {"lexical": LexicalReranker(), "identity": _IdentityReranker()}
    report = await evaluate(HashEmbedder(dim=64), rerankers, PASSAGES, "hash")

    assert report.retrieval.reranker_names == ("lexical", "identity")
    for result in report.retrieval.results:
        # Reranking reorders a shortlist; it must never lose or invent a passage.
        assert set(result.reranked_ids["lexical"]) == set(result.ranked_ids)
        assert len(result.reranked_ids["lexical"]) == len(result.ranked_ids)

    # A reranker that returns its input unchanged cannot move the metric.
    assert report.retrieval.rerank_delta("identity") == pytest.approx(0.0)
