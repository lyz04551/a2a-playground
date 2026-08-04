"""Compatibility facade backed by transactional SQLite persistence."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.persistence.migrate_json import import_legacy_json
from backend.persistence.repository import SQLiteRepository


DATA_DIR = Path(__file__).resolve().parent / "data"
DATABASE_PATH = Path(
    os.getenv("PLAYGROUND_DB_PATH", str(DATA_DIR / "playground.db"))
)
repository = SQLiteRepository(DATABASE_PATH)
repository.initialize()
import_legacy_json(repository, DATA_DIR)


def list_agents() -> list[dict]:
    return repository.list_agents()


def get_agent(agent_id: str) -> Optional[dict]:
    return repository.get_agent(agent_id)


def add_agent(agent: dict) -> dict:
    return repository.upsert_agent(agent)


def delete_agent(agent_id: str) -> bool:
    return repository.delete_agent(agent_id)


def list_conversations() -> list[dict]:
    return repository.list_conversations()


def list_conversations_by_agent(agent_id: str) -> list[dict]:
    return repository.list_conversations(agent_id)


def get_conversation(conversation_id: str) -> Optional[dict]:
    return repository.get_conversation(conversation_id)


def create_conversation(conversation: dict) -> dict:
    return repository.create_conversation(conversation)


def update_conversation(
    conversation_id: str, updates: dict
) -> Optional[dict]:
    updates = {
        **updates,
        "updated_at": datetime.now().isoformat(),
    }
    return repository.update_conversation(conversation_id, updates)


def delete_conversation(conversation_id: str) -> bool:
    return repository.delete_conversation(conversation_id)


def list_messages(
    conversation_id: Optional[str] = None,
) -> list[dict]:
    return repository.list_messages(conversation_id)


def add_message(message: dict) -> dict:
    return repository.add_message(message)


def get_message(message_id: str) -> Optional[dict]:
    return repository.get_message(message_id)


def list_events(
    conversation_id: Optional[str] = None,
) -> list[dict]:
    return repository.list_events(conversation_id)


def add_event(event: dict) -> dict:
    return repository.add_event(event)


def get_events_for_conversation(
    conversation_id: str,
) -> list[dict]:
    return repository.list_events(conversation_id)
