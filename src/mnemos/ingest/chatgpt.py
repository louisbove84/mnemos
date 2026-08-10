"""Parse ChatGPT / OpenAI data-export conversations.json (and zip wrappers)."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mnemos.ingest.models import Conversation, Message

PROVIDER = "openai"


def _from_unix(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            return "\n".join(str(p) for p in parts if p is not None).strip()
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
    return str(content).strip()


def _walk_mapping(mapping: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return message nodes in approximate conversation order via parent chain."""
    # Prefer linearize via current_node if present; else topological by children.
    nodes: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in mapping.items():
        message = node.get("message")
        if not message:
            continue
        author = (message.get("author") or {}).get("role")
        if author in (None, "system"):
            # Keep system only if it has useful content later; skip empty system.
            text = _text_from_content(message.get("content"))
            if not text:
                continue
        nodes.append((node_id, node))

    # Sort by create_time when available.
    def sort_key(item: tuple[str, dict[str, Any]]) -> float:
        msg = item[1].get("message") or {}
        ct = msg.get("create_time")
        try:
            return float(ct) if ct is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    nodes.sort(key=sort_key)
    return nodes


def parse_conversation_object(
    raw: dict[str, Any], *, source_path: str | None = None
) -> Conversation:
    conversation_id = str(raw.get("id") or raw.get("conversation_id") or "")
    if not conversation_id:
        raise ValueError("conversation missing id")

    title = str(raw.get("title") or "Untitled")
    mapping = raw.get("mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError(f"conversation {conversation_id}: mapping must be an object")

    messages: list[Message] = []
    ordinal = 0
    for node_id, node in _walk_mapping(mapping):
        message = node.get("message") or {}
        author = (message.get("author") or {}).get("role") or "unknown"
        content = _text_from_content(message.get("content"))
        if not content:
            continue
        # Normalize ChatGPT roles toward archive roles.
        role = "assistant" if author == "assistant" else author
        if role == "tool":
            role = "assistant"
        mid = str(message.get("id") or node_id)
        messages.append(
            Message(
                id=mid,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=_from_unix(message.get("create_time")),
                ordinal=ordinal,
            )
        )
        ordinal += 1

    return Conversation(
        id=conversation_id,
        provider=PROVIDER,
        title=title,
        created_at=_from_unix(raw.get("create_time")),
        updated_at=_from_unix(raw.get("update_time")),
        source_path=source_path,
        messages=messages,
    )


def parse_conversations_json(data: Any, *, source_path: str | None = None) -> list[Conversation]:
    if isinstance(data, dict) and "conversations" in data:
        data = data["conversations"]
    if not isinstance(data, list):
        raise ValueError("expected a list of conversations")
    out: list[Conversation] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        conv = parse_conversation_object(item, source_path=source_path)
        if conv.messages:
            out.append(conv)
    return out


def load_conversations_from_json_file(path: Path) -> list[Conversation]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return parse_conversations_json(data, source_path=str(path))


def load_conversations_from_zip(path: Path) -> list[Conversation]:
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith("conversations.json")]
        if not names:
            # Some exports nest under a folder; also accept bare conversations.json
            names = [n for n in zf.namelist() if Path(n).name == "conversations.json"]
        if not names:
            raise ValueError(f"{path}: no conversations.json in zip")
        # Prefer the shortest path (top-level export).
        names.sort(key=len)
        with zf.open(names[0]) as fh:
            data = json.loads(fh.read().decode("utf-8"))
        return parse_conversations_json(data, source_path=str(path))


def discover_exports(inbox: Path) -> list[Path]:
    """Find ChatGPT export artifacts in the inbox (non-recursive files + one level)."""
    if not inbox.exists():
        return []
    found: list[Path] = []
    for path in sorted(inbox.iterdir()):
        if path.is_file():
            if path.name == "conversations.json" or path.suffix.lower() == ".zip":
                found.append(path)
        elif path.is_dir():
            candidate = path / "conversations.json"
            if candidate.is_file():
                found.append(candidate)
            for zip_path in sorted(path.glob("*.zip")):
                found.append(zip_path)
    return found


def load_export(path: Path) -> list[Conversation]:
    if path.suffix.lower() == ".zip":
        return load_conversations_from_zip(path)
    return load_conversations_from_json_file(path)
