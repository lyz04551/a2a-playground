import pytest
from sqlalchemy import create_engine, inspect


EXPECTED_TABLES = {
    "agents",
    "conversations",
    "messages",
    "events",
    "orchestration_runs",
    "orchestration_tasks",
    "remote_task_bindings",
    "approvals",
    "artifacts",
}


def _upgrade_database(database_url: str) -> None:
    try:
        from backend.persistence.migrate import upgrade_database
    except ModuleNotFoundError:
        pytest.fail("backend.persistence.migrate is not implemented")
    upgrade_database(database_url)


def test_upgrade_creates_all_business_tables(postgres_url):
    _upgrade_database(postgres_url)
    engine = create_engine(postgres_url)
    try:
        assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_is_idempotent(postgres_url):
    _upgrade_database(postgres_url)
    _upgrade_database(postgres_url)


def test_upgrade_creates_unique_run_sequence_index(postgres_url):
    _upgrade_database(postgres_url)
    engine = create_engine(postgres_url)
    try:
        indexes = {
            index["name"]: index
            for index in inspect(engine).get_indexes("events")
        }
        run_sequence = indexes["ix_events_run_sequence"]
        assert run_sequence["unique"] is True
        assert "run_id IS NOT NULL" in run_sequence["dialect_options"][
            "postgresql_where"
        ]
    finally:
        engine.dispose()
