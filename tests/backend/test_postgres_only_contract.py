from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_has_no_sqlite_persistence_or_memory_checkpointer():
    targets = [
        *sorted((PROJECT_ROOT / "backend").rglob("*.py")),
        *sorted(
            (PROJECT_ROOT / "agents" / "shared-runtime").rglob("*.py")
        ),
        PROJECT_ROOT / "docker-compose.yml",
    ]
    forbidden = (
        "SQLiteRepository",
        "PLAYGROUND_DB_PATH",
        "sqlite_insert",
        "PRAGMA journal_mode",
        "import_legacy_json",
        "MemorySaver",
    )
    offenders = {
        str(path.relative_to(PROJECT_ROOT)): [
            token for token in forbidden if token in path.read_text()
        ]
        for path in targets
        if path.is_file()
        and any(token in path.read_text() for token in forbidden)
    }
    assert offenders == {}
