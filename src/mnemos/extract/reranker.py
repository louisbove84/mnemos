"""Cross-encoders that reorder Graphiti's search hits without calling a hosted API.

Three options, chosen by ``MNEMOS_RERANKER``:

- ``llm``     asks the in-cluster llm Service a yes/no relevance question per passage
              and ranks by the probability it assigned to "True".
- ``bge``     runs a purpose-built cross-encoder locally via sentence-transformers.
- ``lexical`` counts query-term coverage. No model, no network, so it is the fallback
              for tests and for bring-up before llm is reachable.
"""

from __future__ import annotations

import asyncio
import logging
import math

from graphiti_core.cross_encoder.client import CrossEncoderClient
from openai import AsyncOpenAI

from mnemos.config import Settings

log = logging.getLogger(__name__)

# Words that appear in almost every passage, so matching them says nothing about
# relevance. Kept short deliberately: this list only has to carry the fallback.
STOPWORDS = frozenset(
    """
    a an and are as at be but by for from has have how i in into is it its of on or that
    the their then there these they this to was were what when where which who why will with
    you your do does did can could should would we us our my me not no if
    """.split()
)


def _content_terms(text: str) -> set[str]:
    return {word for word in text.lower().split() if word and word not in STOPWORDS}


class LexicalReranker(CrossEncoderClient):
    """Ranks by how much of the query a passage covers.

    Scoring is the fraction of the query's content words that appear in the passage.
    It deliberately does not divide by passage length, which would rank a short
    irrelevant passage above a long relevant one. Passages that tie keep the order
    they arrived in, so with no lexical evidence the embedder's ranking survives.
    """

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        wanted = _content_terms(query)
        if not wanted:
            return [(passage, 0.0) for passage in passages]

        scored = [
            (passage, len(wanted & _content_terms(passage)) / len(wanted)) for passage in passages
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


# Graphiti's own OpenAI reranker pins logit_bias to OpenAI's token ids for True/False,
# which address unrelated tokens under any other tokenizer. We ask the same question
# but read the answer out of top_logprobs by string, so the tokenizer does not matter.
RERANK_SYSTEM_PROMPT = (
    "You judge whether a passage is relevant to a query. Answer with one word: True or False."
)

RERANK_USER_TEMPLATE = """Respond with "True" if PASSAGE is relevant to QUERY, \
and "False" otherwise.
<PASSAGE>
{passage}
</PASSAGE>
<QUERY>
{query}
</QUERY>"""

# Ask for several candidates: a small model often puts whitespace or punctuation in the
# top slot, and the informative token is just below it.
TOP_LOGPROBS = 5


class LLMReranker(CrossEncoderClient):
    """Scores relevance with the local LLM's own confidence, not its sampled answer.

    Reading the probability of the "True" token rather than the emitted text matters:
    at 0.5B the sampled token disagrees with the model's own ranking often enough that
    a text-matching reranker would be close to noise.

    Never raises on a per-passage failure. If every call fails the original order is
    returned unchanged, so an unreachable LLM degrades recall quality instead of
    breaking recall outright.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        concurrency: int = 4,
        timeout: float = 60.0,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self._model = model
        self._concurrency = concurrency

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []

        semaphore = asyncio.Semaphore(self._concurrency)
        scores = await asyncio.gather(
            *(self._score(semaphore, query, passage) for passage in passages)
        )

        if all(score is None for score in scores):
            log.warning("reranker scored no passages; leaving order unchanged")
            return [(passage, 0.0) for passage in passages]

        scored = [
            (passage, 0.0 if score is None else score)
            for passage, score in zip(passages, scores, strict=True)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    async def _score(
        self,
        semaphore: asyncio.Semaphore,
        query: str,
        passage: str,
    ) -> float | None:
        async with semaphore:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": RERANK_USER_TEMPLATE.format(passage=passage, query=query),
                        },
                    ],
                    temperature=0.0,
                    max_tokens=1,
                    logprobs=True,
                    top_logprobs=TOP_LOGPROBS,
                )
            except Exception:
                log.warning("rerank call failed for one passage", exc_info=True)
                return None

        return _probability_of_true(response)


def _probability_of_true(response: object) -> float | None:
    """Pull P(True) out of the first token's alternatives.

    Falls back to 1 - P(False) when the model offered only the negative token, and
    gives up rather than guessing when it offered neither.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    logprobs = getattr(choices[0], "logprobs", None)
    content = getattr(logprobs, "content", None)
    if not content:
        return None
    alternatives = getattr(content[0], "top_logprobs", None)
    if not alternatives:
        return None

    # Prefer the direct measurement wherever the model offered it, even if it ranked
    # "False" higher. Inferring from the negative is the weaker estimate of the two.
    for alternative in alternatives:
        if alternative.token.strip().lower().startswith("true"):
            return math.exp(alternative.logprob)
    for alternative in alternatives:
        if alternative.token.strip().lower().startswith("false"):
            return 1.0 - math.exp(alternative.logprob)
    return None


def build_reranker(settings: Settings) -> CrossEncoderClient:
    """Pick the cross-encoder named by settings.reranker."""
    if settings.reranker == "lexical":
        return LexicalReranker()
    if settings.reranker == "bge":
        # Imported here so sentence-transformers and its ~2GB of weights stay an
        # opt-in extra rather than a hard dependency of the ingest image.
        from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient

        return BGERerankerClient()  # type: ignore[no-untyped-call]
    return LLMReranker(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        concurrency=settings.rerank_concurrency,
    )
