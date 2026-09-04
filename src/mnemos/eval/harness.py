"""Scores an embedder, and the reranker layered on top of it, against the labeled set."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient

from mnemos.eval.dataset import (
    PHRASE_PAIRS,
    RETRIEVAL_CASES,
    CaseKind,
    Passage,
    PhrasePair,
    RetrievalCase,
)
from mnemos.eval.metrics import cosine_similarity, mean, recall_at_k, reciprocal_rank

log = logging.getLogger(__name__)

DEFAULT_RERANK_DEPTH = 5


@dataclass(frozen=True)
class PairResult:
    pair: PhrasePair
    score: float


@dataclass(frozen=True)
class PairReport:
    results: tuple[PairResult, ...]

    def _mean_of(self, kind: str) -> float:
        return mean([r.score for r in self.results if r.pair.kind == kind])

    @property
    def related_mean(self) -> float:
        return self._mean_of("related")

    @property
    def unrelated_mean(self) -> float:
        return self._mean_of("unrelated")

    @property
    def near_duplicate_mean(self) -> float:
        return self._mean_of("near_duplicate")

    @property
    def separation(self) -> float:
        """The headline number: how far related pairs sit above unrelated ones.

        Near zero means the vectors encode nothing useful, whatever their width.
        """
        return self.related_mean - self.unrelated_mean


@dataclass(frozen=True)
class CaseResult:
    case: RetrievalCase
    ranked_ids: tuple[str, ...]
    # Final order per reranker name, so one embedding run can score several of them.
    reranked_ids: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class RetrievalReport:
    results: tuple[CaseResult, ...]
    reranker_names: tuple[str, ...]

    def _cases(self, kind: CaseKind | None) -> list[CaseResult]:
        if kind is None:
            return list(self.results)
        return [r for r in self.results if r.case.kind == kind]

    def case_count(self, kind: CaseKind | None = None) -> int:
        return len(self._cases(kind))

    def mrr(self, kind: CaseKind | None = None) -> float:
        return mean([reciprocal_rank(r.ranked_ids, r.case.relevant_ids) for r in self._cases(kind)])

    def recall_at_1(self, kind: CaseKind | None = None) -> float:
        return mean([recall_at_k(r.ranked_ids, r.case.relevant_ids, 1) for r in self._cases(kind)])

    def recall_at_3(self, kind: CaseKind | None = None) -> float:
        return mean([recall_at_k(r.ranked_ids, r.case.relevant_ids, 3) for r in self._cases(kind)])

    def reranked_mrr(self, name: str, kind: CaseKind | None = None) -> float:
        return mean(
            [reciprocal_rank(r.reranked_ids[name], r.case.relevant_ids) for r in self._cases(kind)]
        )

    def reranked_recall_at_1(self, name: str, kind: CaseKind | None = None) -> float:
        return mean(
            [recall_at_k(r.reranked_ids[name], r.case.relevant_ids, 1) for r in self._cases(kind)]
        )

    def rerank_delta(self, name: str, kind: CaseKind | None = None) -> float:
        """Positive means the reranker improved on the embedding order.

        A reranker that cannot clear zero here is worse than not having one, since it
        only ever sees passages the embedder already ranked highly.
        """
        return self.reranked_mrr(name, kind) - self.mrr(kind)


@dataclass(frozen=True)
class EvalReport:
    label: str
    dimension: int
    pairs: PairReport
    retrieval: RetrievalReport


async def embed_all(embedder: EmbedderClient, texts: Sequence[str]) -> list[list[float]]:
    """Embed a list of texts, preferring one batched call.

    Not every OpenAI-compatible server accepts an array for `input`, so a provider
    that rejects the batch falls back to one call per text rather than failing.
    """
    try:
        return await embedder.create_batch(list(texts))
    except Exception:
        log.warning("batch embedding failed, falling back to one call per text", exc_info=True)
        return [await embedder.create(text) for text in texts]


async def score_pairs(embedder: EmbedderClient) -> PairReport:
    texts: list[str] = []
    for pair in PHRASE_PAIRS:
        texts.extend((pair.left, pair.right))
    vectors = await embed_all(embedder, texts)

    results = [
        PairResult(pair=pair, score=cosine_similarity(vectors[2 * i], vectors[2 * i + 1]))
        for i, pair in enumerate(PHRASE_PAIRS)
    ]
    return PairReport(results=tuple(results))


async def score_retrieval(
    embedder: EmbedderClient,
    rerankers: Mapping[str, CrossEncoderClient],
    passages: Sequence[Passage],
    rerank_depth: int = DEFAULT_RERANK_DEPTH,
) -> RetrievalReport:
    passage_vectors = await embed_all(embedder, [p.text for p in passages])
    query_vectors = await embed_all(embedder, [c.query for c in RETRIEVAL_CASES])
    id_by_text = {p.text: p.id for p in passages}
    text_by_id = {p.id: p.text for p in passages}

    results: list[CaseResult] = []
    for case, query_vector in zip(RETRIEVAL_CASES, query_vectors, strict=True):
        scored = sorted(
            (
                (cosine_similarity(query_vector, vector), passage.id)
                for passage, vector in zip(passages, passage_vectors, strict=True)
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        ranked_ids = tuple(identifier for _, identifier in scored)

        # A reranker only ever sees a shortlist in production, so measure it the same
        # way: reorder the embedder's top hits and leave the tail untouched. Every
        # reranker gets the identical shortlist, which is what makes them comparable.
        head = ranked_ids[:rerank_depth]
        shortlist = [text_by_id[i] for i in head]

        reranked: dict[str, tuple[str, ...]] = {}
        for name, reranker in rerankers.items():
            ordered = await reranker.rank(case.query, list(shortlist))
            reranked[name] = (
                tuple(id_by_text[text] for text, _ in ordered) + ranked_ids[rerank_depth:]
            )

        results.append(CaseResult(case=case, ranked_ids=ranked_ids, reranked_ids=reranked))

    return RetrievalReport(results=tuple(results), reranker_names=tuple(rerankers))


async def evaluate(
    embedder: EmbedderClient,
    rerankers: Mapping[str, CrossEncoderClient],
    passages: Sequence[Passage],
    label: str,
) -> EvalReport:
    pairs = await score_pairs(embedder)
    retrieval = await score_retrieval(embedder, rerankers, passages)
    probe = await embedder.create("dimension probe")
    return EvalReport(label=label, dimension=len(probe), pairs=pairs, retrieval=retrieval)
