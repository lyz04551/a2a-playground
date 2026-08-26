from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.engine import make_url


@pytest.fixture
def postgres_url():
    admin_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        pytest.fail(f"Postgres test dependencies are unavailable: {exc}")

    parsed = make_url(admin_url)
    if not parsed.drivername.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")

    database_name = f"a2a_test_{uuid.uuid4().hex}"
    psycopg_admin_url = parsed.set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)
    test_url = parsed.set(
        drivername="postgresql+psycopg",
        database=database_name,
    ).render_as_string(hide_password=False)

    with psycopg.connect(psycopg_admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(database_name)
            )
        )

    try:
        yield test_url
    finally:
        with psycopg.connect(
            psycopg_admin_url, autocommit=True
        ) as connection:
            connection.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(database_name)
                )
            )
