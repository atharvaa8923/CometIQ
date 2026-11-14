"""The migrations must produce exactly the schema the models describe."""
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app.db import Base, engine


def test_migrated_schema_matches_models(client):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models changed without a migration — run: alembic revision --autogenerate -m '...'\\n{diff}"


def test_database_is_at_head(client):
    from alembic.script import ScriptDirectory

    from app.migrate import alembic_config

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head
    assert "alembic_version" in inspect(engine).get_table_names()
