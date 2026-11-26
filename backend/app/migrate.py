"""Apply database migrations at startup (Alembic). New schema changes: see README → Database migrations."""
import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import BASE_DIR
from .db import engine

log = logging.getLogger("cometiq.migrate")


def alembic_config() -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return cfg


def migrate() -> None:
    cfg = alembic_config()
    tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # Several instances may start together: only one migrates at a time (released at commit).
            conn.exec_driver_sql("SET LOCAL statement_timeout = 0")  # index builds can take longer than a request may
            conn.exec_driver_sql("SET LOCAL lock_timeout = 0")
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(724001)")
            tables = set(inspect(conn).get_table_names())
        cfg.attributes["connection"] = conn
        if tables and "alembic_version" not in tables:
            log.warning("Database predates migrations: marking it as the baseline revision")
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
