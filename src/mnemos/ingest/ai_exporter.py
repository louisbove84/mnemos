"""Parse AI Exporter (saveai.net) Markdown conversation dumps.

Shared by Gemini and Grok exports, which use the same heading layout:

    > From: https://...
    # you asked
    message time: YYYY-MM-DD HH:MM:SS
    ...
    ---
    # gemini response   # or: # grok response
    ...
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from mnemos.ingest.models import Conversation, Message

FROM_RE = re.compile(r"^>\s*From:\s*(https?\S+)", re.MULTILINE)
TIME_RE = re.compile(r"^message time:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
SECTION_RE = re.compile(
    r"^#\s+(you asked|gemini response|grok response|chatgpt response)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
FOOTER_RE = re.compile(r"^---\s*\nPowered by \[AI Exporter\].*$", re.MULTILINE | re.DOTALL)


def _parse_message_time(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _conversation_id(provider: str, source_url: str | None, path: Path) -> str:
    if source_url:
        parsed = urlparse(source_url)
        # Prefer the last path segment (Gemini app id / Grok conversation id).
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return f"{provider}-{parts[-1]}"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return f"{provider}-{path.stem}-{digest}"


def detect_ai_exporter_provider(text: str) -> str | None:
    """Return provider name if this looks like an AI Exporter dump."""
    from_match = FROM_RE.search(text)
    if from_match:
        host = urlparse(from_match.group(1)).netloc.lower()
        if "gemini.google.com" in host:
            return "gemini"
        if host in {"grok.com", "www.grok.com", "x.com"} or host.endswith(".grok.com"):
            return "grok"
        if "chatgpt.com" in host or "chat.openai.com" in host:
            return "openai"
    lowered = text.lower()
    if re.search(r"^#\s+gemini response\s*$", text, re.MULTILINE | re.IGNORECASE):
        return "gemini"
    if re.search(r"^#\s+grok response\s*$", text, re.MULTILINE | re.IGNORECASE):
        return "grok"
    if "powered by [ai exporter]" in lowered and "# you asked" in lowered:
        return "unknown"
    return None


def parse_ai_exporter_markdown(
    text: str,
    *,
    provider: str,
    source_path: str | None = None,
    title: str | None = None,
) -> Conversation:
    text = FOOTER_RE.sub("", text).strip()
    from_match = FROM_RE.search(text)
    source_url = from_match.group(1) if from_match else None

    path = Path(source_path) if source_path else Path("export.md")
    conversation_id = _conversation_id(provider, source_url, path)
    conv_title = title or path.stem.replace("-", " ").replace("_", " ")

    matches = list(SECTION_RE.finditer(text))
    if not matches:
        raise ValueError(f"{source_path or 'export'}: no AI Exporter sections found")

    messages: list[Message] = []
    ordinal = 0
    for index, match in enumerate(matches):
        heading = match.group(1).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # Drop leading --- separators left from the exporter template.
        body = re.sub(r"^---\s*", "", body).strip()
        body = re.sub(r"\n---\s*$", "", body).strip()

        time_match = TIME_RE.search(body)
        created_at = _parse_message_time(time_match.group(1)) if time_match else None
        if time_match:
            body = body[time_match.end() :].strip()
        body = re.sub(r"^---\s*", "", body).strip()
        if not body:
            continue

        role = "user" if heading == "you asked" else "assistant"

        messages.append(
            Message(
                id=f"{conversation_id}-m{ordinal}",
                conversation_id=conversation_id,
                role=role,
                content=body,
                created_at=created_at,
                ordinal=ordinal,
            )
        )
        ordinal += 1

    if not messages:
        raise ValueError(f"{source_path or 'export'}: no messages parsed")

    return Conversation(
        id=conversation_id,
        provider=provider,
        title=conv_title,
        created_at=messages[0].created_at,
        updated_at=messages[-1].created_at,
        source_path=source_path,
        messages=messages,
    )


def load_ai_exporter_file(path: Path, *, provider: str | None = None) -> Conversation:
    text = path.read_text(encoding="utf-8")
    detected = detect_ai_exporter_provider(text)
    resolved = provider or detected
    if resolved is None or resolved == "unknown":
        raise ValueError(f"{path}: could not detect AI Exporter provider")
    return parse_ai_exporter_markdown(
        text,
        provider=resolved,
        source_path=str(path),
        title=path.stem,
    )
