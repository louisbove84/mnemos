"""CLI for the extraction evaluation: `mnemos-eval-extract`.

Sends Graphiti's own `extract_nodes` prompt to the configured LLM and scores what comes
back. Rendering the real prompt is the point: a hand-written prompt would measure a model
against text mnemos never sends, and the failure being tested for is caused by the shape of
Graphiti's prompt in particular — roughly five thousand characters of few-shot examples
sitting after the transcript.

Extraction runs through `/v1/chat/completions` with a `json_schema`, matching the
`OpenAIGenericClient` the ingest path uses, so a model that scores well here is being
measured on the endpoint it will actually be called on.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, cast

from graphiti_core.prompts.extract_nodes import ExtractedEntities, extract_message
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema

from mnemos.config import Settings, get_settings
from mnemos.eval.extraction import (
    EXTRACTION_CASES,
    CaseScore,
    ExtractionCase,
    ExtractionReport,
    score_case,
)

log = logging.getLogger(__name__)

# Graphiti configures 512 in the ingest path. The eval defaults higher so that a looping
# model is scored on its output rather than being cut off and reported as a parse error,
# which is what the first investigation ran into.
DEFAULT_MAX_TOKENS = 2048


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mnemos-eval-extract",
        description="Measure whether extraction reads the transcript or the prompt's examples.",
    )
    parser.add_argument("--base-url", help="Override MNEMOS_LLM_BASE_URL.")
    parser.add_argument("--model", help="Override MNEMOS_LLM_MODEL.")
    parser.add_argument("--label", help="Name for this run in the output. Defaults to the model.")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--verbose", action="store_true", help="Show per-case entity lists.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args(argv)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {}
    if args.base_url:
        overrides["llm_base_url"] = args.base_url
    if args.model:
        overrides["llm_model"] = args.model
    return settings.model_copy(update=overrides) if overrides else settings


def _prompt_for(case: ExtractionCase) -> list[ChatCompletionMessageParam]:
    context: dict[str, Any] = {
        "episode_content": case.episode,
        "previous_episodes": [],
        "custom_prompt": "",
        "custom_extraction_instructions": "",
        "entity_types": None,
        "source_description": "conversation export",
        "ensure_ascii": False,
    }
    return [
        cast(ChatCompletionMessageParam, {"role": m.role, "content": m.content})
        for m in extract_message(context)
    ]


def _response_format() -> ResponseFormatJSONSchema:
    return cast(
        ResponseFormatJSONSchema,
        {
            "type": "json_schema",
            "json_schema": {
                "name": "ExtractedEntities",
                "schema": ExtractedEntities.model_json_schema(),
                "strict": True,
            },
        },
    )


def _run_case(client: OpenAI, model: str, case: ExtractionCase, max_tokens: int) -> CaseScore:
    response = client.chat.completions.create(
        model=model,
        messages=_prompt_for(case),
        max_tokens=max_tokens,
        temperature=0.0,
        response_format=_response_format(),
    )
    choice = response.choices[0]
    overran = choice.finish_reason == "length"
    raw = choice.message.content or ""

    try:
        payload = json.loads(raw)
        names = [str(e.get("name", "")) for e in payload.get("extracted_entities", [])]
    except json.JSONDecodeError:
        # Constrained decoding still emits invalid JSON if the model runs out of tokens
        # mid-string. Recover the names already committed rather than scoring the case zero,
        # so a looping model is visible as looping instead of as a broken endpoint.
        names = _salvage_names(raw)
        log.warning("case %s returned unparseable JSON; salvaged %d names", case.id, len(names))

    return score_case(case, names, overran=overran)


def _salvage_names(raw: str) -> list[str]:
    """Pull complete "name": "..." pairs out of a truncated JSON object."""
    names: list[str] = []
    for fragment in raw.split('"name"')[1:]:
        opening = fragment.find('"', fragment.find(":"))
        if opening == -1:
            continue
        closing = fragment.find('"', opening + 1)
        if closing == -1:
            continue
        names.append(fragment[opening + 1 : closing])
    return names


def _format_report(report: ExtractionReport, verbose: bool) -> str:
    lines = [
        f"{report.label}",
        "  as returned by the model",
        f"    recall         {report.recall:.3f}   (expected entities recovered)",
        f"    contamination  {report.contamination_rate:.3f}   "
        "(entities lifted from the prompt's examples; must be 0)",
        f"    looped         {report.looped}/{len(report.scores)} cases",
        f"    verdict        {'usable' if report.usable else 'NOT usable'}",
        "  after dropping entities absent from the transcript",
        f"    recall         {report.filtered_recall:.3f}",
        f"    contamination  {report.filtered_contamination_rate:.3f}",
        f"    verdict        {'usable' if report.filtered_usable else 'NOT usable'}",
    ]
    if verbose:
        for score in report.scores:
            lines.append(f"  {score.case.id}")
            lines.append(f"    extracted    {list(score.extracted)}")
            lines.append(f"    kept         {list(score.kept)}")
            lines.append(f"    found        {list(score.found)}")
            lines.append(f"    missing      {list(score.missing)}")
            lines.append(f"    contaminated {list(score.contaminated)}")
            lines.append(f"    ungrounded   {list(score.ungrounded)}")
            lines.append(f"    duplicates   {score.duplicates}   overran {score.overran}")
    return "\n".join(lines)


def _to_dict(report: ExtractionReport) -> dict[str, Any]:
    return {
        "label": report.label,
        "recall": report.recall,
        "contamination_rate": report.contamination_rate,
        "looped": report.looped,
        "usable": report.usable,
        "filtered_recall": report.filtered_recall,
        "filtered_contamination_rate": report.filtered_contamination_rate,
        "filtered_usable": report.filtered_usable,
        "cases": [
            {
                "id": s.case.id,
                "extracted": list(s.extracted),
                "kept": list(s.kept),
                "found": list(s.found),
                "missing": list(s.missing),
                "contaminated": list(s.contaminated),
                "ungrounded": list(s.ungrounded),
                "duplicates": s.duplicates,
                "overran": s.overran,
                "recall": s.recall,
                "contamination_rate": s.contamination_rate,
            }
            for s in report.scores
        ],
    }


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    settings = _apply_overrides(get_settings(), args)

    client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "not-needed")
    label = args.label or f"{settings.llm_model} at {settings.llm_base_url}"

    try:
        scores = tuple(
            _run_case(client, settings.llm_model, case, args.max_tokens)
            for case in EXTRACTION_CASES
        )
    except Exception as exc:
        log.error("extraction evaluation failed against %s: %s", settings.llm_base_url, exc)
        sys.exit(1)

    report = ExtractionReport(label=label, scores=scores)

    if args.json:
        print(json.dumps(_to_dict(report), indent=2))
        return

    print(f"mnemos extraction evaluation\n  {len(EXTRACTION_CASES)} transcripts\n")
    print(_format_report(report, args.verbose))


if __name__ == "__main__":
    main()
