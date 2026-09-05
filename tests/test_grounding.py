"""The grounding filter that keeps Graphiti's prompt examples out of the graph."""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from graphiti_core.utils.maintenance import node_operations

from mnemos.extract.grounding import (
    NODE_EXTRACTION_PROMPTS,
    current_episode,
    filter_entities,
    is_grounded,
)

EPISODE = (
    "user: I want to hike near Aurora this Saturday.\n"
    "assistant: Try the Cedar Ridge Loop near Aurora.\n"
    "user: Also remember my dog's name is Nimbus."
)


def _entities(*names: str) -> dict[str, Any]:
    return {"extracted_entities": [{"name": n, "entity_type_id": 0} for n in names]}


def _names(response: dict[str, Any]) -> list[str]:
    return [e["name"] for e in response["extracted_entities"]]


def test_entities_from_the_transcript_survive() -> None:
    response = filter_entities(_entities("Nimbus", "Cedar Ridge Loop", "Aurora"), EPISODE)
    assert _names(response) == ["Nimbus", "Cedar Ridge Loop", "Aurora"]


def test_graphiti_prompt_examples_are_removed() -> None:
    """The exact names the first cluster run wrote into Neo4j."""
    response = filter_entities(
        _entities("Nimbus", "Nisha's dad", "Jordan's dog", "Mustang", "Gamecube"),
        EPISODE,
    )
    assert _names(response) == ["Nimbus"]


def test_repeated_names_collapse_to_one() -> None:
    """A looping model returned the same entity 88 times in one episode."""
    response = filter_entities(_entities(*["Cedar Ridge Loop"] * 88), EPISODE)
    assert _names(response) == ["Cedar Ridge Loop"]


def test_possessive_qualification_is_kept() -> None:
    """Graphiti asks for "Nisha's dad" over "dad", so assembled names must survive."""
    episode = "user: Nisha said her dad is visiting next week"
    response = filter_entities(_entities("Nisha's dad"), episode)
    assert _names(response) == ["Nisha's dad"]


def test_unrelated_keys_in_the_response_are_preserved() -> None:
    payload: dict[str, Any] = {**_entities("Nimbus"), "some_other_field": 7}
    response = filter_entities(payload, EPISODE)
    assert response["some_other_field"] == 7


def test_a_response_without_entities_passes_through_untouched() -> None:
    """Other prompts share this client; a non-extraction payload must not be mangled."""
    payload: dict[str, Any] = {"duplicate_facts": [1, 2]}
    assert filter_entities(payload, EPISODE) == payload


def test_blank_and_malformed_entries_are_dropped() -> None:
    payload: dict[str, Any] = {
        "extracted_entities": [{"name": "  "}, {"nope": 1}, {"name": "Nimbus"}]
    }
    assert _names(filter_entities(payload, EPISODE)) == ["Nimbus"]


@pytest.mark.parametrize(
    ("name", "grounded"),
    [
        ("Cedar Ridge Loop", True),
        ("cedar ridge loop", True),
        ("Nimbus", True),
        ("Mustang", False),
        ("Riverside Park", False),
        ("Belmont Arts Center", False),
    ],
)
def test_grounding_decisions(name: str, grounded: bool) -> None:
    assert is_grounded(name, EPISODE) is grounded


def test_context_variable_defaults_to_unset() -> None:
    """Nothing may leak between episodes; the pipeline resets it after each add_episode."""
    assert current_episode.get() is None


def test_graphiti_still_uses_the_prompt_names_we_filter_on() -> None:
    """Guards the one silent failure mode of this design.

    The filter fires on `prompt_name`. If Graphiti renames those values, filtering stops and
    nothing complains — the graph just quietly fills with prompt examples again. This reads
    the pinned graphiti-core source so the upgrade that would break it fails here first.
    """
    source = inspect.getsource(node_operations)
    for name in NODE_EXTRACTION_PROMPTS:
        assert f"'{name}'" in source or f'"{name}"' in source, (
            f"graphiti-core no longer passes prompt_name={name!r}; "
            "the grounding filter is not running"
        )
