"""Labeled cases for measuring whether the retrieval stack carries meaning.

The phrasings deliberately avoid sharing content words with the thing they should
match. Anything that scores well here has to be matching meaning, because there is
no vocabulary overlap left to match on — which is exactly the property the hash
embedder and the lexical reranker lack.

Subject matter tracks the repository's own fixtures (a hike, defense contractors,
Madison housing) so the numbers speak to the kind of text mnemos actually ingests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PairKind = Literal["related", "unrelated", "near_duplicate"]


@dataclass(frozen=True)
class PhrasePair:
    left: str
    right: str
    kind: PairKind


@dataclass(frozen=True)
class Passage:
    id: str
    text: str


# "topical" cases are answerable by picking the right subject. "discriminative" ones put
# several same-subject passages in play and only one of them answers, which is the work a
# reranker is actually there to do. Reported separately so a rising overall number cannot
# hide a reranker that never earns its latency.
CaseKind = Literal["topical", "discriminative"]


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    relevant_ids: tuple[str, ...]
    kind: CaseKind = "topical"


PHRASE_PAIRS: tuple[PhrasePair, ...] = (
    PhrasePair(
        "Nimbus came along for the Cedar Ridge hike",
        "the dog joined us on that mountain trail",
        "related",
    ),
    PhrasePair(
        "are defense primes safer investments than startups",
        "do established military contractors carry less risk than new ventures",
        "related",
    ),
    PhrasePair(
        "Madison rentals are impossible to find right now",
        "the housing market in Wisconsin's capital is extremely tight",
        "related",
    ),
    PhrasePair(
        "what time did we set off for the summit",
        "when exactly was the climb started",
        "related",
    ),
    PhrasePair(
        "I need to reserve a seat on a plane",
        "looking to book airline tickets",
        "related",
    ),
    PhrasePair(
        "Nimbus came along for the Cedar Ridge hike",
        "the housing market in Wisconsin's capital is extremely tight",
        "unrelated",
    ),
    PhrasePair(
        "do established military contractors carry less risk than new ventures",
        "when exactly was the climb started",
        "unrelated",
    ),
    PhrasePair(
        "looking to book airline tickets",
        "the sourdough starter needs feeding twice a day",
        "unrelated",
    ),
    PhrasePair(
        "the dog joined us on that mountain trail",
        "quarterly revenue guidance was revised upward",
        "unrelated",
    ),
    PhrasePair(
        "Madison rentals are impossible to find right now",
        "the timing belt is due for replacement",
        "unrelated",
    ),
    # Near-identical wording, opposite intent. Reported without a verdict: every
    # embedding model scores these high, so they measure a known blind spot rather
    # than a pass or a fail.
    PhrasePair(
        "how do I start the server",
        "how do I stop the server",
        "near_duplicate",
    ),
    PhrasePair(
        "the dog chased the cat",
        "the cat chased the dog",
        "near_duplicate",
    ),
)


PASSAGES: tuple[Passage, ...] = (
    Passage("hike-plan", "We set off before dawn to catch the sunrise from the ridge."),
    Passage("hike-dog", "Nimbus trotted the entire Cedar Ridge Loop without slowing down."),
    Passage("hike-gear", "Packed two litres of water, a shell jacket, and trail snacks."),
    Passage(
        "defense-stability",
        "Lockheed Martin's revenue is anchored by multi-year government programs.",
    ),
    Passage(
        "defense-startup",
        "Vannevar Labs is venture funded, so its runway depends on the next round.",
    ),
    Passage(
        "housing-tight", "Madison's vacancy rate is under two percent and listings go in days."
    ),
    Passage(
        "housing-price", "Median rent in the isthmus neighbourhoods climbed again this spring."
    ),
    Passage("cooking", "The sourdough starter doubles about four hours after feeding."),
    Passage("car", "The timing belt should be replaced somewhere around 100,000 miles."),
    # Same subjects as above, differing on one fact. Embeddings put these beside their
    # topic siblings, so getting them right means reading the passage, not the topic.
    Passage("hike-water", "We ran dry on the descent and refilled from the creek at mile nine."),
    Passage("defense-dividend", "Lockheed has raised its dividend every year for two decades."),
    Passage("housing-buy", "Starter homes on the west side now list above four hundred thousand."),
    Passage("car-done", "I finally got the timing belt swapped at the shop last month."),
    Passage("ops-rollback", "Tuesday's deploy was rolled back once p99 latency tripled."),
    Passage("ops-clean", "Wednesday's release went out cleanly and held all week."),
)


RETRIEVAL_CASES: tuple[RetrievalCase, ...] = (
    RetrievalCase("how did the puppy handle that long walk", ("hike-dog",)),
    RetrievalCase("what time did we leave for the summit", ("hike-plan",)),
    RetrievalCase("which company has the most predictable income", ("defense-stability",)),
    RetrievalCase("why might the young firm run out of money", ("defense-startup",)),
    RetrievalCase("is it difficult to rent an apartment there", ("housing-tight", "housing-price")),
    RetrievalCase("how long until the bread mixture is ready", ("cooking",)),
    RetrievalCase("when should I service the engine", ("car",)),
    # Each of these sits next to a sibling passage the embedder ranks just as highly.
    RetrievalCase("did we have enough to drink out there", ("hike-water",), "discriminative"),
    RetrievalCase(
        "what does that contractor pay its shareholders", ("defense-dividend",), "discriminative"
    ),
    RetrievalCase("what would buying a place there cost me", ("housing-buy",), "discriminative"),
    RetrievalCase("has the belt already been changed", ("car-done",), "discriminative"),
    RetrievalCase("which release did we have to undo", ("ops-rollback",), "discriminative"),
    RetrievalCase("which release stayed up", ("ops-clean",), "discriminative"),
)
