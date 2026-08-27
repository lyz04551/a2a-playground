import pytest


def test_database_url_is_required(monkeypatch):
    try:
        from backend.database import create_repository_from_env
    except (ImportError, AttributeError):
        pytest.fail("create_repository_from_env is not implemented")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        create_repository_from_env()


def test_database_url_rejects_sqlite(monkeypatch):
    try:
        from backend.database import create_repository_from_env
    except (ImportError, AttributeError):
        pytest.fail("create_repository_from_env is not implemented")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
    with pytest.raises(ValueError, match="PostgreSQL"):
        create_repository_from_env()
