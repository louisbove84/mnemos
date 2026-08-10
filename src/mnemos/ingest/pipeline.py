"""Inbox → Postgres archive → Graphiti extraction."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from mnemos.archive import store
from mnemos.config import Settings, get_settings
from mnemos.extract.graphiti_pipeline import extract_conversations
from mnemos.ingest.discover import discover_exports, load_export

log = logging.getLogger(__name__)


def _move_processed(export_path: Path, inbox: Path, processed: Path) -> Path:
    """Move an inbox artifact into processed/, preserving gemini/grok subdirs."""
    try:
        relative = export_path.relative_to(inbox)
    except ValueError:
        relative = Path(export_path.name)
    dest = processed / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.move(str(export_path), str(dest))
    return dest


async def run_ingest(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    inbox = Path(settings.inbox_dir)
    processed = Path(settings.processed_dir)
    processed.mkdir(parents=True, exist_ok=True)

    exports = discover_exports(inbox)
    if not exports:
        log.info("No exports found in %s", inbox)
        return {"exports": 0, "conversations": 0, "messages": 0}

    pool = await store.connect(settings.postgres_dsn)
    await store.ensure_schema(pool)

    total_conversations = 0
    total_messages = 0
    results: list[dict[str, object]] = []

    try:
        for artifact in exports:
            run_id = await store.start_run(pool, str(artifact.path), artifact.provider)
            try:
                conversations = load_export(artifact)
                for conversation in conversations:
                    await store.upsert_conversation(pool, conversation)
                    total_conversations += 1
                    total_messages += len(conversation.messages)

                extract_result = await extract_conversations(settings, conversations)
                await store.finish_run(
                    pool,
                    run_id,
                    conversation_count=len(conversations),
                    message_count=sum(len(c.messages) for c in conversations),
                    status="ok",
                )
                if artifact.path.is_file():
                    _move_processed(artifact.path, inbox, processed)
                results.append(
                    {
                        "path": str(artifact.path),
                        "provider": artifact.provider,
                        "conversations": len(conversations),
                        "extract": extract_result,
                    }
                )
            except Exception as exc:
                log.exception("Ingest failed for %s", artifact.path)
                await store.finish_run(
                    pool,
                    run_id,
                    conversation_count=0,
                    message_count=0,
                    status="error",
                    error=str(exc),
                )
                raise
    finally:
        await pool.close()

    return {
        "exports": len(results),
        "conversations": total_conversations,
        "messages": total_messages,
        "results": results,
    }
