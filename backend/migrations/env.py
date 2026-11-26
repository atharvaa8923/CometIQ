"""Alembic environment: uses CometIQ's models and DATABASE_URL."""
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers all tables on Base.metadata)
from app.config import get_settings
from app.db import Base, include_object

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("url") or get_settings().DATABASE_URL


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = engine_from_config({"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _run(conn)


def _run(conn) -> None:
    # render_as_batch: lets column changes work on SQLite as well as PostgreSQL
    context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True, compare_type=True,
                      include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
