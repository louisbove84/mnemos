"""Unit tests for the ChatGPT export parser (no cluster required)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mnemos.ingest.chatgpt import (
    discover_exports,
    load_conversations_from_json_file,
    load_export,
    parse_conversations_json,
)

FIXTURE = Path(__file__).parent / "fixtures" / "chatgpt_export" / "conversations.json"


def test_parse_fixture_conversation() -> None:
    conversations = load_conversations_from_json_file(FIXTURE)
    assert len(conversations) == 1
    conv = conversations[0]
    assert conv.id == "conv-fixture-aurora"
    assert conv.provider == "openai"
    assert "Aurora" in conv.title
    assert len(conv.messages) == 4
    assert conv.messages[0].role == "user"
    assert "Cedar Ridge Loop" in conv.messages[1].content
    assert "Nimbus" in conv.messages[2].content


def test_parse_wrapped_conversations_key() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    wrapped = {"conversations": raw}
    conversations = parse_conversations_json(wrapped)
    assert len(conversations) == 1


def test_load_export_from_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "chatgpt-export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURE, arcname="conversations.json")
    conversations = load_export(zip_path)
    assert len(conversations) == 1
    assert conversations[0].id == "conv-fixture-aurora"


def test_discover_exports(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "conversations.json"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    found = discover_exports(inbox)
    assert found == [target]
