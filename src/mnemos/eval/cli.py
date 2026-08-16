"""CLI for the retrieval evaluation: `mnemos-eval`.

Runs against any OpenAI-compatible embeddings endpoint, so the same command works
against a port-forwarded cluster Service or an Ollama on the developer's machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient

from mnemos.config import Settings, get_settings
from mnemos.eval.dataset import PASSAGES, PHRASE_PAIRS, RETRIEVAL_CASES
from mnemos.eval.harness import EvalReport, evaluate
from mnemos.extract.embedder import build_embedder
from mnemos.extract.reranker import build_reranker

log = logging.getLogger(__name__)

RERANKER_CHOICES = ("none", "lexical", "llm", "bge")
DEFAULT_RERANKERS = "lexical,llm"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mnemos-eval",
        description="Measure whether the configured embeddings and reranker carry meaning.",
    )
    parser.add_argument("--base-url", help="Override MNEMOS_EMBED_BASE_URL.")
    parser.add_argument("--model", help="Override MNEMOS_EMBED_MODEL.")
    parser.add_argument("--dim", type=int, help="Override MNEMOS_EMBED_DIM.")
    parser.add_argument("--llm-base-url", help="Override MNEMOS_LLM_BASE_URL for the reranker.")
    parser.add_argument("--llm-model", help="Override MNEMOS_LLM_MODEL for the reranker.")
    parser.add_argument(
        "--rerankers",
        default=DEFAULT_RERANKERS,
        help=(
            "Comma-separated rerankers to compare "
            f"({', '.join(RERANKER_CHOICES)}). Default: {DEFAULT_RERANKERS}."
        ),
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip the hash stand-in comparison run.",
    )
    parser.add_argument(
        "--hash-only",
        action="store_true",
        help="Only run the hash stand-in, which needs no embeddings service.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show per-query results.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args(argv)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {}
    if args.base_url:
        overrides["embed_base_url"] = args.base_url
    if args.model:
        overrides["embed_model"] = args.model
    if args.dim:
        overrides["embed_dim"] = args.dim
    if args.llm_base_url:
        overrides["llm_base_url"] = args.llm_base_url
    if args.llm_model:
        overrides["llm_model"] = args.llm_model
    return settings.model_copy(update=overrides) if overrides else settings


def _parse_rerankers(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    unknown = [name for name in names if name not in RERANKER_CHOICES]
    if unknown:
        raise SystemExit(
            f"unknown reranker(s): {', '.join(unknown)}. Choose from {', '.join(RERANKER_CHOICES)}."
        )
    return names


def _build_rerankers(settings: Settings, names: list[str]) -> dict[str, CrossEncoderClient]:
    """Instantiate each named reranker once and reuse it across embedders."""
    return {
        name: build_reranker(settings.model_copy(update={"reranker": name}))
        for name in names
        if name != "none"
    }


def _label(settings: Settings, mode: str) -> str:
    if mode == "hash":
        return "hash stand-in"
    return f"{settings.embed_model} at {settings.embed_base_url}"


def _embedder_for(settings: Settings, mode: str) -> EmbedderClient:
    return build_embedder(settings.model_copy(update={"embedder": mode}))


async def _run(
    settings: Settings,
    modes: list[str],
    reranker_names: list[str],
) -> list[EvalReport]:
    rerankers = _build_rerankers(settings, reranker_names)
    reports: list[EvalReport] = []
    for mode in modes:
        embedder = _embedder_for(settings, mode)
        reports.append(await evaluate(embedder, rerankers, PASSAGES, _label(settings, mode)))
    return reports


def _format_report(report: EvalReport, verbose: bool) -> str:
    pairs = report.pairs
    retrieval = report.retrieval
    lines = [
        f"{report.label}  [{report.dimension}d]",
        f"  phrase pairs     related {pairs.related_mean:+.3f}   "
        f"unrelated {pairs.unrelated_mean:+.3f}   separation {pairs.separation:+.3f}",
        f"  near-duplicates  {pairs.near_duplicate_mean:+.3f}   "
        "(same words, opposite meaning: expected to score high)",
        f"  embeddings only  MRR {retrieval.mrr():.3f}   "
        f"recall@1 {retrieval.recall_at_1():.3f}   recall@3 {retrieval.recall_at_3():.3f}",
    ]
    for name in retrieval.reranker_names:
        lines.append(
            f"  + {name:<12}   MRR {retrieval.reranked_mrr(name):.3f}   "
            f"recall@1 {retrieval.reranked_recall_at_1(name):.3f}   "
            f"({retrieval.rerank_delta(name):+.3f} MRR vs embeddings alone)"
        )

    # Where reranking is supposed to pay for itself: same subject, one right answer.
    lines.append(f"  discriminative cases only ({retrieval.case_count('discriminative')} queries)")
    lines.append(f"    embeddings only  MRR {retrieval.mrr('discriminative'):.3f}")
    for name in retrieval.reranker_names:
        lines.append(
            f"    + {name:<12}   MRR {retrieval.reranked_mrr(name, 'discriminative'):.3f}   "
            f"({retrieval.rerank_delta(name, 'discriminative'):+.3f})"
        )
    if verbose:
        lines.append("  per query:")
        for result in retrieval.results:
            want = ", ".join(result.case.relevant_ids)
            hit = "OK " if result.ranked_ids[0] in result.case.relevant_ids else "MISS"
            tops = "   ".join(
                f"{name}: {ids[0]}" for name, ids in sorted(result.reranked_ids.items())
            )
            lines.append(
                f"    {hit} {result.case.query!r}\n"
                f"         top: {result.ranked_ids[0]}   want: {want}\n"
                f"         after rerank   {tops}"
            )
    return "\n".join(lines)


def _to_dict(report: EvalReport) -> dict[str, Any]:
    return {
        "label": report.label,
        "dimension": report.dimension,
        "pairs": {
            "related_mean": report.pairs.related_mean,
            "unrelated_mean": report.pairs.unrelated_mean,
            "near_duplicate_mean": report.pairs.near_duplicate_mean,
            "separation": report.pairs.separation,
            "scores": [
                {"left": r.pair.left, "right": r.pair.right, "kind": r.pair.kind, "score": r.score}
                for r in report.pairs.results
            ],
        },
        "retrieval": {
            "mrr": report.retrieval.mrr(),
            "recall_at_1": report.retrieval.recall_at_1(),
            "recall_at_3": report.retrieval.recall_at_3(),
            "discriminative_mrr": report.retrieval.mrr("discriminative"),
            "rerankers": {
                name: {
                    "mrr": report.retrieval.reranked_mrr(name),
                    "recall_at_1": report.retrieval.reranked_recall_at_1(name),
                    "delta": report.retrieval.rerank_delta(name),
                    "discriminative_mrr": report.retrieval.reranked_mrr(name, "discriminative"),
                    "discriminative_delta": report.retrieval.rerank_delta(name, "discriminative"),
                }
                for name in report.retrieval.reranker_names
            },
            "cases": [
                {
                    "query": r.case.query,
                    "kind": r.case.kind,
                    "relevant_ids": list(r.case.relevant_ids),
                    "ranked_ids": list(r.ranked_ids),
                    "reranked_ids": {name: list(ids) for name, ids in r.reranked_ids.items()},
                }
                for r in report.retrieval.results
            ],
        },
    }


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    settings = _apply_overrides(get_settings(), args)
    reranker_names = _parse_rerankers(args.rerankers)

    if args.hash_only:
        modes = ["hash"]
    elif args.no_baseline:
        modes = ["openai_compatible"]
    else:
        modes = ["openai_compatible", "hash"]

    try:
        reports = asyncio.run(_run(settings, modes, reranker_names))
    except Exception as exc:
        # Almost always an unreachable embeddings service; say so instead of a traceback.
        log.error("evaluation failed against %s: %s", settings.embed_base_url, exc)
        sys.exit(1)

    if args.json:
        print(json.dumps([_to_dict(r) for r in reports], indent=2))
        return

    print(
        f"mnemos retrieval evaluation\n"
        f"  {len(PASSAGES)} passages, {len(RETRIEVAL_CASES)} queries, "
        f"{len(PHRASE_PAIRS)} phrase pairs\n"
    )
    for report in reports:
        print(_format_report(report, args.verbose))
        print()


if __name__ == "__main__":
    main()
