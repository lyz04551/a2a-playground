"""Compatibility facade backed by transactional Postgres persistence."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from backend.persistence.repository import DatabaseRepository


def create_repository_from_env() -> DatabaseRepository:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return DatabaseRepository(database_url)


repository = create_repository_from_env()


def list_agents() -> list[dict]:
    return repository.list_agents()


def get_agent(agent_id: str) -> Optional[dict]:
    return repository.get_agent(agent_id)


def add_agent(agent: dict) -> dict:
    return repository.upsert_agent(agent)


def delete_agent(agent_id: str) -> bool:
    return repository.delete_agent(agent_id)


def list_conversations(*, limit: int | None = None, offset: int = 0) -> list[dict]:
    return repository.list_conversations(limit=limit, offset=offset)


def list_conversations_by_agent(agent_id: str, *, limit: int | None = None, offset: int = 0) -> list[dict]:
    return repository.list_conversations(agent_id, limit=limit, offset=offset)


def count_conversations(agent_id: str | None = None) -> int:
    return repository.count_conversations(agent_id)


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
    conversation_id: Optional[str] = None, *, limit: int | None = None, offset: int = 0,
) -> list[dict]:
    return repository.list_events(conversation_id, limit=limit, offset=offset)


def count_events(conversation_id: Optional[str] = None) -> int:
    return repository.count_events(conversation_id)


def add_event(event: dict) -> dict:
    return repository.add_event(event)


def get_events_for_conversation(
    conversation_id: str,
) -> list[dict]:
    return repository.list_events(conversation_id)
