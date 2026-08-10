"""Unit tests for Gemini/Grok AI Exporter Markdown parsers."""

from __future__ import annotations

from pathlib import Path

from mnemos.ingest.ai_exporter import detect_ai_exporter_provider, load_ai_exporter_file
from mnemos.ingest.discover import discover_exports, load_export
from mnemos.ingest.gemini import load_export as load_gemini
from mnemos.ingest.grok import load_export as load_grok

GEMINI_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "gemini_export"
    / "Lockheed-Martin-vs.-Vannevar-Labs-Stability.md"
)
GROK_FIXTURE = (
    Path(__file__).parent / "fixtures" / "grok_export" / "Madison-WI-Housing-Market-Tight.md"
)


def test_parse_gemini_fixture() -> None:
    conversations = load_gemini(GEMINI_FIXTURE)
    assert len(conversations) == 1
    conv = conversations[0]
    assert conv.provider == "gemini"
    assert conv.id.startswith("gemini-")
    assert "Lockheed" in conv.title or "Vannevar" in conv.title
    assert conv.messages[0].role == "user"
    assert "lockheed" in conv.messages[0].content.lower()
    assert conv.messages[1].role == "assistant"
    assert "Vannevar" in conv.messages[1].content
    assert conv.messages[0].created_at is not None


def test_parse_grok_fixture() -> None:
    conversations = load_grok(GROK_FIXTURE)
    assert len(conversations) == 1
    conv = conversations[0]
    assert conv.provider == "grok"
    assert conv.id.startswith("grok-")
    assert conv.messages[0].role == "user"
    assert "Madison" in conv.messages[0].content
    assert conv.messages[1].role == "assistant"
    assert "seller" in conv.messages[1].content.lower()


def test_detect_providers() -> None:
    assert detect_ai_exporter_provider(GEMINI_FIXTURE.read_text(encoding="utf-8")) == "gemini"
    assert detect_ai_exporter_provider(GROK_FIXTURE.read_text(encoding="utf-8")) == "grok"


def test_discover_provider_subdirs(tmp_path: Path) -> None:
    gemini_dir = tmp_path / "gemini"
    grok_dir = tmp_path / "grok"
    gemini_dir.mkdir()
    grok_dir.mkdir()
    g = gemini_dir / "chat.md"
    k = grok_dir / "chat.md"
    g.write_text(GEMINI_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    k.write_text(GROK_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    found = discover_exports(tmp_path)
    providers = {item.provider for item in found}
    assert providers == {"gemini", "grok"}
    by_provider = {item.provider: item for item in found}
    gemini_conv = load_export(by_provider["gemini"])[0]
    grok_conv = load_export(by_provider["grok"])[0]
    assert gemini_conv.provider == "gemini"
    assert grok_conv.provider == "grok"


def test_load_ai_exporter_autodetect() -> None:
    conv = load_ai_exporter_file(GEMINI_FIXTURE)
    assert conv.provider == "gemini"
