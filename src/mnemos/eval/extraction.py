"""Measure whether extraction reads the transcript or Graphiti's own prompt examples.

The retrieval harness in [`dataset.py`][mnemos.eval.dataset] scores ranking over passages
that are already correct, so it cannot see a fabricated fact. That is the failure which
actually broke the first cluster run: qwen2.5-0.5b returned `Nisha's dad` and `Jordan's dog`,
names that appear nowhere in any transcript and only inside Graphiti's few-shot prompt. Every
retrieval number looked fine while the graph was fiction.

So the signal here is contamination, not ranking. Each case pairs a transcript with the
entities a competent extractor should find, and scoring asks three questions:

1. Did the expected entities appear at all?
2. Did anything come from the prompt's examples instead?
3. Did the model loop, repeating one name until it ran out of tokens?

A model can score zero recall and zero contamination by returning nothing, so recall and
contamination are always reported together.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_PUNCTUATION = re.compile(r"[^\w\s'-]+")
_WHITESPACE = re.compile(r"\s+")
_POSSESSIVE = re.compile(r"'s\b")


def normalize(name: str) -> str:
    """Lowercase and strip punctuation so 'Cedar Ridge Loop.' matches 'cedar ridge loop'."""
    lowered = _PUNCTUATION.sub(" ", name.lower())
    return _WHITESPACE.sub(" ", lowered).strip()


@dataclass(frozen=True)
class ExtractionCase:
    """One transcript and the entities extraction should recover from it.

    `expected` is deliberately short. It holds the entities whose absence would make the
    memory useless, not everything a generous reader might list, because a long list turns
    recall into a judgement call about how thorough the labeller was feeling.
    """

    id: str
    episode: str
    expected: tuple[str, ...]


# Names that exist only inside graphiti_core's few-shot examples. An extractor returning
# these is copying the instructions instead of reading the input.
#
# Curated by hand rather than scraped out of the prompt, because the two overlap: Graphiti's
# own example mentions Lockheed Martin ("My spouse started a new role at Lockheed Martin"),
# and the Gemini fixture is genuinely about Lockheed Martin. Scraping would mark a correct
# extraction as contamination. Same for Denver, which is plausible transcript content.
#
# Tied to the graphiti-core version in poetry.lock. If that moves, re-read
# graphiti_core/prompts/extract_nodes.py before trusting these numbers.
PROMPT_EXAMPLE_NAMES: tuple[str, ...] = (
    "nisha",
    "nisha's dad",
    "jordan",
    "jordan lee",
    "jordan's dog",
    "jordan's cat",
    "alex",
    "nate",
    "mina",
    "priya",
    "gamecube",
    "mustang",
    "ford mustang",
    "belmont arts center",
    "riverside park",
    "acme corp",
    "siam kitchen",
    "elm street",
    "moen faucet",
    "pad see ew",
)


# Transcripts match the repository fixtures, so these numbers describe the text mnemos
# actually ingests rather than a benchmark written to be winnable.
EXTRACTION_CASES: tuple[ExtractionCase, ...] = (
    ExtractionCase(
        id="aurora-hike",
        episode=(
            "user: I want to hike near Aurora this Saturday. Suggest a moderate trail "
            "and what to pack.\n"
            "assistant: Try the Cedar Ridge Loop near Aurora. Pack water, a rain shell, "
            "and trail snacks. The overlook has the best view after mile two.\n"
            "user: Great. Also remember my dog's name is Nimbus.\n"
            "assistant: Got it - Nimbus can join on leash. Cedar Ridge Loop allows dogs "
            "on weekdays and Saturdays."
        ),
        expected=("nimbus", "cedar ridge loop", "aurora"),
    ),
    ExtractionCase(
        id="defense-employers",
        episode=(
            "user: Stability of working at lockheed martin vs vannevar labs\n"
            "assistant: Comparing stability between a defense prime like Lockheed Martin "
            "and a venture-backed defense tech startup like Vannevar Labs comes down to "
            "revenue base. Lockheed is anchored by multi-year government programs, while "
            "Vannevar depends on its next funding round."
        ),
        expected=("lockheed martin", "vannevar labs"),
    ),
    ExtractionCase(
        id="madison-housing",
        episode=(
            "user: How's the housing market in Madison WI\n"
            "assistant: Madison, WI's housing market remains a competitive seller's market "
            "as of mid-2026, with modest price growth, low inventory, and homes often "
            "selling above asking within days."
        ),
        expected=("madison",),
    ),
)


@dataclass(frozen=True)
class CaseScore:
    """What one model did with one transcript.

    Carries both the raw entity list and the list surviving a grounding filter, so one run
    answers two questions: how good is the model, and how good is the model plus a cheap
    deterministic check. Reporting only the first would leave the obvious remedy unmeasured.
    """

    case: ExtractionCase
    extracted: tuple[str, ...]
    kept: tuple[str, ...]
    found: tuple[str, ...]
    missing: tuple[str, ...]
    contaminated: tuple[str, ...]
    ungrounded: tuple[str, ...]
    duplicates: int
    overran: bool

    @property
    def recall(self) -> float:
        if not self.case.expected:
            return 0.0
        return len(self.found) / len(self.case.expected)

    @property
    def filtered_recall(self) -> float:
        """Recall after dropping ungrounded entities.

        Should equal `recall`, since an expected entity is by definition present in the
        transcript. Computed rather than assumed so that a filter which is too aggressive
        shows up as lost recall instead of hiding.
        """
        if not self.case.expected:
            return 0.0
        kept = set(self.kept)
        survived = [e for e in self.case.expected if any(e in k or k in e for k in kept)]
        return len(survived) / len(self.case.expected)

    @property
    def filtered_contamination_rate(self) -> float:
        if not self.kept:
            return 0.0
        return len([n for n in self.kept if n in PROMPT_EXAMPLE_NAMES]) / len(self.kept)

    @property
    def contamination_rate(self) -> float:
        """Share of returned entities lifted from the prompt's examples.

        Zero is the only acceptable value. Anything above it means the model is answering
        from the instructions, and the graph is describing Graphiti rather than the user.
        """
        if not self.extracted:
            return 0.0
        return len(self.contaminated) / len(self.extracted)


def is_grounded(name: str, episode: str) -> bool:
    """Does this entity name have any footing in the transcript?

    Graphiti asks for possessive qualification ("Nisha's dad" rather than "dad"), so a
    correct entity is not always a substring of the source. Requiring every significant
    word to appear is the compromise: it accepts a constructed name built from words that
    are present, and rejects one assembled out of nothing.

    Possessive endings are dropped from both sides first, because the transcript says
    "Nisha said her dad" while the entity is "Nisha's dad" — grammatically different,
    the same evidence.
    """
    haystack = _POSSESSIVE.sub("", normalize(episode))
    words = [w for w in _POSSESSIVE.sub("", normalize(name)).split() if len(w) > 2]
    if not words:
        return normalize(name) in haystack
    return all(word in haystack for word in words)


def score_case(
    case: ExtractionCase,
    extracted: Sequence[str],
    *,
    overran: bool = False,
) -> CaseScore:
    normalized = [normalize(name) for name in extracted if name.strip()]
    unique = set(normalized)

    found = tuple(
        expected
        for expected in case.expected
        if any(expected in name or name in expected for name in unique)
    )
    missing = tuple(e for e in case.expected if e not in found)

    # A name only counts as contamination when it is absent from the transcript. Otherwise a
    # fixture that legitimately discusses an example subject would be scored as a failure.
    contaminated = tuple(
        sorted(
            name
            for name in unique
            if name in PROMPT_EXAMPLE_NAMES and not is_grounded(name, case.episode)
        )
    )
    ungrounded = tuple(sorted(name for name in unique if not is_grounded(name, case.episode)))

    return CaseScore(
        case=case,
        extracted=tuple(normalized),
        kept=tuple(sorted(name for name in unique if is_grounded(name, case.episode))),
        found=found,
        missing=missing,
        contaminated=contaminated,
        ungrounded=ungrounded,
        duplicates=len(normalized) - len(unique),
        overran=overran,
    )


@dataclass(frozen=True)
class ExtractionReport:
    label: str
    scores: tuple[CaseScore, ...]

    @property
    def recall(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.recall for s in self.scores) / len(self.scores)

    @property
    def contamination_rate(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.contamination_rate for s in self.scores) / len(self.scores)

    @property
    def filtered_recall(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.filtered_recall for s in self.scores) / len(self.scores)

    @property
    def filtered_contamination_rate(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.filtered_contamination_rate for s in self.scores) / len(self.scores)

    @property
    def looped(self) -> int:
        """Cases where the model repeated itself or ran to the token ceiling."""
        return sum(1 for s in self.scores if s.overran or s.duplicates > 0)

    @property
    def usable(self) -> bool:
        """Would this model produce a graph worth querying?

        Recall above half with no contamination and no looping. Deliberately strict: a graph
        holding one invented fact ranks that fact first for every query, so a little
        contamination is not a little problem.
        """
        return self.recall >= 0.5 and self.contamination_rate == 0.0 and self.looped == 0

    @property
    def filtered_usable(self) -> bool:
        """The same bar applied to entities surviving the grounding filter.

        Looping is not a gate here because the filter deduplicates, so a model that repeats
        one name ninety times contributes it once. An overrun still matters and stays in the
        per-case detail, since output cut off mid-list may have lost entities never emitted.
        """
        return self.filtered_recall >= 0.5 and self.filtered_contamination_rate == 0.0
