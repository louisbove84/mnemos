"""Discover provider export artifacts in the hostPath inbox."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mnemos.ingest import chatgpt, gemini, grok
from mnemos.ingest.ai_exporter import detect_ai_exporter_provider, load_ai_exporter_file
from mnemos.ingest.models import Conversation


@dataclass(frozen=True)
class ExportArtifact:
    path: Path
    provider: str


def discover_exports(inbox: Path) -> list[ExportArtifact]:
    """Find ingestible exports.

    Layout:
      inbox/conversations.json | *.zip          → openai
      inbox/gemini/*.md                         → gemini
      inbox/grok/*.md                           → grok
      inbox/*.md (AI Exporter, detected by URL) → gemini|grok
    """
    if not inbox.exists():
        return []

    found: list[ExportArtifact] = []

    for path in chatgpt.discover_exports(inbox):
        found.append(ExportArtifact(path=path, provider="openai"))

    for provider, subdir in (("gemini", inbox / "gemini"), ("grok", inbox / "grok")):
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("*.md")):
            found.append(ExportArtifact(path=path, provider=provider))

    # Top-level Markdown dumps (AI Exporter) when the user drops files flat.
    for path in sorted(inbox.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        detected = detect_ai_exporter_provider(text)
        if detected in {"gemini", "grok"}:
            found.append(ExportArtifact(path=path, provider=detected))

    # De-dupe by path (chatgpt discover may overlap with nothing today).
    seen: set[Path] = set()
    unique: list[ExportArtifact] = []
    for item in found:
        if item.path in seen:
            continue
        seen.add(item.path)
        unique.append(item)
    return unique


def load_export(artifact: ExportArtifact) -> list[Conversation]:
    if artifact.provider == "openai":
        return chatgpt.load_export(artifact.path)
    if artifact.provider == "gemini":
        return gemini.load_export(artifact.path)
    if artifact.provider == "grok":
        return grok.load_export(artifact.path)
    # Fallback: try AI Exporter auto-detect.
    return [load_ai_exporter_file(artifact.path)]
