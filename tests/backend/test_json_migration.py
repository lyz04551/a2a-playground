from __future__ import annotations

import json

from backend.persistence.migrate_json import import_legacy_json
from backend.persistence.repository import SQLiteRepository


def write_json(path, name, value):
    (path / name).write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def test_legacy_json_imports_once_without_modifying_source_files(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    agents = [
        {"id": "ops", "name": "Ops", "url": "http://ops"},
    ]
    conversations = [
        {
            "id": "conv-1",
            "agent_id": "ops",
            "title": "Existing chat",
            "type": "single",
        }
    ]
    messages = [
        {
            "id": "msg-1",
            "conversation_id": "conv-1",
            "role": "user",
            "content": "hello",
        }
    ]
    events = [
        {
            "id": "evt-1",
            "conversation_id": "conv-1",
            "task_id": "task-1",
            "event_type": "working",
        }
    ]
    for filename, value in (
        ("agents.json", agents),
        ("conversations.json", conversations),
        ("messages.json", messages),
        ("events.json", events),
    ):
        write_json(data_dir, filename, value)
    before = {
        path.name: path.read_bytes() for path in data_dir.glob("*.json")
    }

    repository = SQLiteRepository(tmp_path / "playground.db")
    repository.initialize()
    first = import_legacy_json(repository, data_dir)
    second = import_legacy_json(repository, data_dir)

    assert first == {
        "agents": 1,
        "conversations": 1,
        "messages": 1,
        "events": 1,
    }
    assert second == {
        "agents": 0,
        "conversations": 0,
        "messages": 0,
        "events": 0,
    }
    assert repository.list_agents()[0]["id"] == "ops"
    assert {
        path.name: path.read_bytes() for path in data_dir.glob("*.json")
    } == before
