"""Scoring behaviour for the extraction evaluation.

The scorer is pure, so the cases that matter are checkable without a model: does a
transcript-derived entity count as found, does an example-derived one count as
contamination, and does a name that legitimately appears in both escape being penalised.
"""

from __future__ import annotations

from mnemos.eval.extraction import (
    EXTRACTION_CASES,
    PROMPT_EXAMPLE_NAMES,
    ExtractionCase,
    ExtractionReport,
    is_grounded,
    normalize,
    score_case,
)

HIKE = ExtractionCase(
    id="test-hike",
    episode="user: hiking the Cedar Ridge Loop near Aurora with my dog Nimbus",
    expected=("nimbus", "cedar ridge loop", "aurora"),
)


def test_normalize_strips_case_and_punctuation() -> None:
    assert normalize("  Cedar Ridge Loop.  ") == "cedar ridge loop"
    assert normalize("Nisha's dad") == "nisha's dad"


def test_perfect_extraction_scores_full_recall_without_contamination() -> None:
    score = score_case(HIKE, ["Nimbus", "Cedar Ridge Loop", "Aurora"])
    assert score.recall == 1.0
    assert score.contamination_rate == 0.0
    assert score.missing == ()
    assert score.duplicates == 0


def test_prompt_example_names_are_counted_as_contamination() -> None:
    """The observed 0.5B failure: every name comes from Graphiti's instructions."""
    score = score_case(HIKE, ["Nisha", "Jordan", "Nisha's dad", "Jordan's dog"])
    assert score.recall == 0.0
    assert score.contamination_rate == 1.0
    assert "nisha's dad" in score.contaminated


def test_repeated_names_are_reported_as_duplicates() -> None:
    score = score_case(HIKE, ["Nisha's dad"] * 4)
    assert score.duplicates == 3


def test_example_name_present_in_the_transcript_is_not_contamination() -> None:
    """Graphiti's examples mention Lockheed Martin and so does a real fixture.

    Scoring has to distinguish "returned a name from the prompt" from "returned a name that
    happens to appear in both", or the defense-employers case fails for being correct.
    """
    case = ExtractionCase(
        id="test-defense",
        episode="user: stability of working at Lockheed Martin vs Vannevar Labs",
        expected=("lockheed martin", "vannevar labs"),
    )
    score = score_case(case, ["Lockheed Martin", "Vannevar Labs"])
    assert score.contaminated == ()
    assert score.recall == 1.0


def test_grounding_accepts_possessive_qualification_but_rejects_invention() -> None:
    episode = "user: Nisha said her dad is visiting"
    # Graphiti asks for "Nisha's dad" rather than "dad"; both words are present.
    assert is_grounded("Nisha's dad", episode)
    assert not is_grounded("Jordan's dog", episode)


def test_returning_nothing_is_not_scored_as_success() -> None:
    """Zero contamination is trivially achievable by silence, so recall must gate it."""
    report = ExtractionReport(label="silent", scores=(score_case(HIKE, []),))
    assert report.contamination_rate == 0.0
    assert report.recall == 0.0
    assert not report.usable


def test_overrun_marks_the_report_as_looped() -> None:
    report = ExtractionReport(
        label="looping",
        scores=(score_case(HIKE, ["Nimbus", "Cedar Ridge Loop", "Aurora"], overran=True),),
    )
    assert report.recall == 1.0
    assert report.looped == 1
    assert not report.usable


def test_grounding_filter_removes_contamination_without_costing_recall() -> None:
    """The proposed remedy, measured: drop entities absent from the transcript.

    This is the observed 1.5B and 3B behaviour in miniature — correct entities mixed with
    example names. The filter has to remove the latter and keep the former, or it is not
    worth preferring over a larger model.
    """
    score = score_case(
        HIKE,
        ["Nimbus", "Cedar Ridge Loop", "Aurora", "Gamecube", "Mustang", "Riverside Park"],
    )
    assert score.contamination_rate > 0.0
    assert score.filtered_contamination_rate == 0.0
    assert score.filtered_recall == 1.0
    assert set(score.kept) == {"nimbus", "cedar ridge loop", "aurora"}


def test_grounding_filter_collapses_a_looping_model() -> None:
    """Ninety repetitions of one name become one entity, so looping stops mattering."""
    score = score_case(HIKE, ["Cedar Ridge Loop"] * 90, overran=True)
    assert score.duplicates == 89
    assert score.kept == ("cedar ridge loop",)


def test_usable_requires_recall_and_cleanliness_together() -> None:
    report = ExtractionReport(
        label="good",
        scores=(score_case(HIKE, ["Nimbus", "Cedar Ridge Loop", "Aurora"]),),
    )
    assert report.usable


def test_expected_entities_are_grounded_in_their_own_transcripts() -> None:
    """Guards the dataset itself: an unfindable label would make recall unreachable."""
    for case in EXTRACTION_CASES:
        for expected in case.expected:
            assert expected in normalize(case.episode), f"{case.id}: {expected!r} not in transcript"


def test_no_expected_entity_is_also_a_contaminant() -> None:
    """A label on both lists would be scored as correct and fabricated at once."""
    for case in EXTRACTION_CASES:
        overlap = set(case.expected) & set(PROMPT_EXAMPLE_NAMES)
        assert not overlap, f"{case.id}: {overlap} is both expected and a contaminant"
