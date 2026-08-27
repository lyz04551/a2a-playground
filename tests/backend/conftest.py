from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_backend_database(postgres_url, monkeypatch):
    monkeypatch.setenv("TEST_ACTIVE_DATABASE_URL", postgres_url)
    monkeypatch.setenv("DATABASE_URL", postgres_url)
