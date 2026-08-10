"""Gemini conversation exports (AI Exporter Markdown)."""

from __future__ import annotations

from pathlib import Path

from mnemos.ingest.ai_exporter import load_ai_exporter_file
from mnemos.ingest.models import Conversation

PROVIDER = "gemini"


def load_export(path: Path) -> list[Conversation]:
    return [load_ai_exporter_file(path, provider=PROVIDER)]
