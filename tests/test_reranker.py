"""Reranker tests. No service needed: the LLM path is driven through a stubbed score."""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

import pytest

from mnemos.config import Settings
from mnemos.extract.reranker import (
    LexicalReranker,
    LLMReranker,
    _probability_of_true,
    build_reranker,
)


def _response(*tokens: tuple[str, float]) -> SimpleNamespace:
    """Build the nested shape the OpenAI client returns for logprobs."""
    alternatives = [SimpleNamespace(token=token, logprob=logprob) for token, logprob in tokens]
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                logprobs=SimpleNamespace(content=[SimpleNamespace(top_logprobs=alternatives)])
            )
        ]
    )


def test_probability_of_true_reads_the_true_token() -> None:
    score = _probability_of_true(_response(("True", math.log(0.8)), ("False", math.log(0.2))))
    assert score == pytest.approx(0.8)


def test_probability_of_true_ignores_position() -> None:
    """The informative token is often not the most likely one on a small model."""
    score = _probability_of_true(_response(("\n", math.log(0.5)), ("True", math.log(0.4))))
    assert score == pytest.approx(0.4)


def test_probability_of_true_inverts_a_false_only_answer() -> None:
    score = _probability_of_true(_response(("False", math.log(0.9))))
    assert score == pytest.approx(0.1)


def test_probability_of_true_prefers_the_direct_measurement() -> None:
    """ "False" ranking higher must not stop us reading P(True) straight off."""
    score = _probability_of_true(_response(("False", math.log(0.9)), ("True", math.log(0.08))))
    assert score == pytest.approx(0.08)


def test_probability_of_true_gives_up_on_an_unusable_answer() -> None:
    assert _probability_of_true(_response(("maybe", math.log(0.9)))) is None
    assert _probability_of_true(_response()) is None
    assert _probability_of_true(SimpleNamespace(choices=[])) is None


class _StubReranker(LLMReranker):
    """LLMReranker with the network call replaced by a lookup table."""

    def __init__(self, scores: dict[str, float | None]) -> None:
        super().__init__(base_url="http://unused/v1", api_key="unused", model="stub")
        self._stub_scores = scores

    async def _score(
        self,
        semaphore: asyncio.Semaphore,
        query: str,
        passage: str,
    ) -> float | None:
        return self._stub_scores[passage]


@pytest.mark.asyncio
async def test_llm_reranker_orders_by_probability() -> None:
    reranker = _StubReranker({"low": 0.1, "high": 0.9, "mid": 0.5})
    ranked = await reranker.rank("q", ["low", "high", "mid"])
    assert [passage for passage, _ in ranked] == ["high", "mid", "low"]


@pytest.mark.asyncio
async def test_llm_reranker_keeps_passages_whose_call_failed() -> None:
    """A dropped passage would silently remove a real answer from recall."""
    reranker = _StubReranker({"good": 0.9, "broken": None, "poor": 0.2})
    ranked = await reranker.rank("q", ["good", "broken", "poor"])
    assert {passage for passage, _ in ranked} == {"good", "broken", "poor"}
    assert ranked[0][0] == "good"


@pytest.mark.asyncio
async def test_llm_reranker_fails_open_when_the_service_is_down() -> None:
    reranker = _StubReranker({"a": None, "b": None})
    ranked = await reranker.rank("q", ["a", "b"])
    assert [passage for passage, _ in ranked] == ["a", "b"]


@pytest.mark.asyncio
async def test_llm_reranker_handles_an_empty_shortlist() -> None:
    assert await _StubReranker({}).rank("q", []) == []


@pytest.mark.asyncio
async def test_lexical_reranker_ignores_stopwords() -> None:
    """Matching only filler words must not look like relevance."""
    ranked = dict(
        await LexicalReranker().rank(
            "how do I configure the embedder",
            ["it is on the of and to", "configure the embedder here"],
        )
    )
    assert ranked["it is on the of and to"] == 0.0
    assert ranked["configure the embedder here"] > 0.0


@pytest.mark.asyncio
async def test_lexical_reranker_does_not_reward_short_passages() -> None:
    """The previous scoring divided by passage length, which ranked this backwards."""
    long_relevant = "the embedder writes vectors " + "and other detail " * 20
    ranked = await LexicalReranker().rank("embedder vectors", ["tangent", long_relevant])
    assert ranked[0][0] == long_relevant


@pytest.mark.asyncio
async def test_lexical_reranker_leaves_ties_in_input_order() -> None:
    """With no lexical evidence the embedder's ranking should survive untouched."""
    passages = ["zebra", "apple", "mango"]
    ranked = await LexicalReranker().rank("unrelated query terms", passages)
    assert [passage for passage, _ in ranked] == passages


@pytest.mark.asyncio
async def test_lexical_reranker_handles_an_all_stopword_query() -> None:
    passages = ["one", "two"]
    ranked = await LexicalReranker().rank("the and of", passages)
    assert [passage for passage, _ in ranked] == passages


def test_build_reranker_selects_by_setting() -> None:
    assert isinstance(build_reranker(Settings(reranker="lexical")), LexicalReranker)
    assert isinstance(build_reranker(Settings(reranker="llm")), LLMReranker)
