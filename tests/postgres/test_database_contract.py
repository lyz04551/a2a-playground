from sqlalchemy import create_engine, text


def test_postgres_fixture_provides_a_real_isolated_database(postgres_url):
    engine = create_engine(postgres_url)
    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("select current_database()")
            ).scalar_one()
            assert database_name.startswith("a2a_test_")
    finally:
        engine.dispose()
