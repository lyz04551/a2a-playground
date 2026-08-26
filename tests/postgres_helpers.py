from __future__ import annotations

import os

from backend.persistence.migrate import upgrade_database
from backend.persistence.repository import DatabaseRepository


def create_test_repository() -> DatabaseRepository:
    database_url = os.environ["TEST_ACTIVE_DATABASE_URL"]
    upgrade_database(database_url)
    return DatabaseRepository(database_url)
