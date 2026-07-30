from __future__ import annotations

import json
from pathlib import Path

from .repository import SQLiteRepository


MIGRATION_ID = "legacy-json-v1"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def import_legacy_json(
    repository: SQLiteRepository, data_dir: str | Path
) -> dict[str, int]:
    empty = {
        "agents": 0,
        "conversations": 0,
        "messages": 0,
        "events": 0,
    }
    if repository.has_migration(MIGRATION_ID):
        return empty

    directory = Path(data_dir)
    agent_rows = _read(directory / "agents.json")
    conversation_rows = _read(directory / "conversations.json")
    message_rows = _read(directory / "messages.json")
    event_rows = _read(directory / "events.json")

    for row in agent_rows:
        repository.upsert_agent(row)
    repository.import_legacy_rows(
        conversation_rows=conversation_rows,
        message_rows=message_rows,
        event_rows=event_rows,
    )
    counts = {
        "agents": len(agent_rows),
        "conversations": len(conversation_rows),
        "messages": len(message_rows),
        "events": len(event_rows),
    }
    repository.mark_migration(MIGRATION_ID, counts)
    return counts
