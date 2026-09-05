"""Discard extracted entities that do not appear in the episode they came from.

Graphiti's node-extraction prompt carries roughly 4,900 characters of few-shot examples after
the transcript, formatted as `Message: "..."` blocks that look structurally identical to the
real input. Small local models extract from the examples: the first cluster run produced
`Nisha's dad`, `Jordan's dog`, `Mustang` and `Gamecube`, none of which appear in any
transcript and all of which appear in `graphiti_core/prompts/extract_nodes.py`.

Model size does not fix this. Measured with `mnemos-eval-extract`, qwen2.5-3b contaminates at
0.287 against the 0.5B's 0.348 — six times the parameters, no improvement. What does fix it is
refusing to believe an entity that is not in the source text, which takes contamination to
zero at every model size and costs no recall, because a real entity is by definition present
in its own transcript.

See [ADR 0011](../../../docs/adr/0011-grounded-entity-extraction.md).
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from typing import Any

from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message
from pydantic import BaseModel

log = logging.getLogger(__name__)

_PUNCTUATION = re.compile(r"[^\w\s'-]+")
_WHITESPACE = re.compile(r"\s+")
_POSSESSIVE = re.compile(r"'s\b")

# Words shorter than this are ignored when checking grounding. "of" and "the" appear in almost
# any text and would wave through names built entirely from filler.
MIN_SIGNIFICANT_WORD = 3

# Graphiti tags each LLM call with the prompt that produced it. Only node extraction is
# filtered: attribute extraction and deduplication legitimately reason about text that is not
# the current episode, and filtering them would break resolution against existing entities.
#
# These names come from `graphiti_core.utils.maintenance.node_operations._call_extraction_llm`
# and are pinned by poetry.lock. A test asserts they still exist, because if Graphiti renames
# them this filter silently stops running and the graph quietly fills with prompt examples
# again.
NODE_EXTRACTION_PROMPTS = frozenset(
    {
        "extract_nodes.extract_message",
        "extract_nodes.extract_text",
        "extract_nodes.extract_json",
    }
)

# The episode currently being ingested. Set by the extraction pipeline around add_episode,
# which is the only place that knows the source text — Graphiti does not pass it down to the
# LLM client. A ContextVar rather than an attribute so concurrent episodes cannot read each
# other's text.
current_episode: ContextVar[str | None] = ContextVar("current_episode", default=None)


def _normalize(text: str) -> str:
    lowered = _PUNCTUATION.sub(" ", text.lower())
    return _POSSESSIVE.sub("", _WHITESPACE.sub(" ", lowered).strip())


def is_grounded(name: str, episode: str) -> bool:
    """Does every significant word of this entity name appear in the episode?

    Not a substring test. Graphiti asks for possessive qualification — "Nisha's dad" rather
    than the bare "dad" — so a correct entity is often assembled rather than quoted. Requiring
    the words to be present accepts a name built from the transcript and rejects one built
    from nothing, which is the distinction that matters.

    This does let through a name whose words are scattered across an unrelated part of the
    episode. That is the deliberate trade: the check is cheap, deterministic, and never
    discards a real entity, which matters more than catching every questionable one.
    """
    haystack = _normalize(episode)
    words = [w for w in _normalize(name).split() if len(w) >= MIN_SIGNIFICANT_WORD]
    if not words:
        return _normalize(name) in haystack
    return all(word in haystack for word in words)


def filter_entities(response: dict[str, Any], episode: str) -> dict[str, Any]:
    """Drop ungrounded entities from a node-extraction response, and deduplicate it.

    Deduplication matters as much as the filter. A looping model returned the same name
    eighty-eight times in one episode, and Graphiti would otherwise resolve each copy
    separately.
    """
    entities = response.get("extracted_entities")
    if not isinstance(entities, list):
        return response

    kept: list[Any] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for entity in entities:
        name = entity.get("name", "") if isinstance(entity, dict) else ""
        if not isinstance(name, str) or not name.strip():
            continue
        if not is_grounded(name, episode):
            dropped.append(name)
            continue
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        kept.append(entity)

    if dropped:
        # Logged at info because this is expected and routine, not an error. It is the only
        # visibility into how much the extraction model is inventing on real exports.
        log.info(
            "dropped %d ungrounded entit%s: %s",
            len(dropped),
            "y" if len(dropped) == 1 else "ies",
            ", ".join(sorted(set(dropped))[:10]),
        )

    return {**response, "extracted_entities": kept}


class GroundedEntityClient(OpenAIGenericClient):
    """An OpenAI-compatible client that will not report entities absent from the source.

    Wraps rather than reimplements, so schema handling, retries and error mapping stay
    Graphiti's. The only behaviour added is discarding entities the transcript does not
    support.
    """

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: Any = None,
        group_id: str | None = None,
        prompt_name: str | None = None,
        *,
        attribute_extraction: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "response_model": response_model,
            "max_tokens": max_tokens,
            "group_id": group_id,
            "prompt_name": prompt_name,
            "attribute_extraction": attribute_extraction,
        }
        # Only forward model_size when the caller set it, so Graphiti's own default applies.
        if model_size is not None:
            kwargs["model_size"] = model_size

        response = await super().generate_response(messages, **kwargs)

        if prompt_name not in NODE_EXTRACTION_PROMPTS:
            return response

        episode = current_episode.get()
        if episode is None:
            # Extraction ran outside the pipeline's context manager. Filtering blind would be
            # worse than not filtering, so say so loudly instead.
            log.warning(
                "node extraction ran with no episode in context; entities not grounded "
                "(prompt=%s, group_id=%s)",
                prompt_name,
                group_id,
            )
            return response

        return filter_entities(response, episode)


def build_llm_client(settings_llm_config: LLMConfig, max_tokens: int) -> GroundedEntityClient:
    return GroundedEntityClient(config=settings_llm_config, max_tokens=max_tokens)
