from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from backend.persistence.migrate import upgrade_database


@contextmanager
def _repository(postgres_url):
    try:
        from backend.persistence.repository import DatabaseRepository
    except ImportError:
        pytest.fail("DatabaseRepository is not implemented")
    upgrade_database(postgres_url)
    instance = DatabaseRepository(postgres_url)
    try:
        yield instance
    finally:
        instance.engine.dispose()


def test_repository_rejects_non_postgres_urls():
    try:
        from backend.persistence.repository import DatabaseRepository
    except ImportError:
        pytest.fail("DatabaseRepository is not implemented")
    with pytest.raises(ValueError, match="PostgreSQL"):
        DatabaseRepository("sqlite:///local.db")


def test_agent_upsert_keeps_stable_ids(postgres_url):
    with _repository(postgres_url) as repository:
        repository.upsert_agent(
            {"id": "ops", "name": "Operations", "url": "http://old"}
        )
        repository.upsert_agent(
            {"id": "ops", "name": "Operations", "url": "http://new"}
        )

        assert repository.list_agents() == [
            {"id": "ops", "name": "Operations", "url": "http://new"}
        ]


def test_concurrent_messages_update_count_without_lost_writes(postgres_url):
    with _repository(postgres_url) as repository:
        repository.create_conversation(
            {"id": "conv-1", "agent_id": "ops", "message_count": 0}
        )

        def add_message(index: int) -> None:
            repository.add_message(
                {
                    "id": f"message-{index}",
                    "conversation_id": "conv-1",
                    "role": "user",
                    "content": str(index),
                }
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(add_message, range(12)))

        conversation = repository.get_conversation("conv-1")
        assert conversation["message_count"] == 12
        assert conversation["updated_at"]
