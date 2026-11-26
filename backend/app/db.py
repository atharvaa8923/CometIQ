from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
if _is_sqlite:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True,
                           connect_args={"check_same_thread": False, "timeout": settings.DB_LOCK_TIMEOUT_MS / 1000})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute(f"PRAGMA busy_timeout={settings.DB_LOCK_TIMEOUT_MS}")
        cur.close()
else:
    # Pool sized per app instance; statement, lock and idle-transaction timeouts stop one slow query from holding everyone up.
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_S,
        pool_recycle=settings.DB_POOL_RECYCLE_S,
        connect_args={
            "application_name": "cometiq",
            "connect_timeout": 10,
            "options": (f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS} -c lock_timeout={settings.DB_LOCK_TIMEOUT_MS} "
                        f"-c idle_in_transaction_session_timeout={settings.DB_IDLE_TX_TIMEOUT_MS}"),
        },
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def savepoint(db):
    """A savepoint for an insert that may lose a race (a unique key taken by a concurrent request): on PostgreSQL only
    the failed insert is undone. The sqlite3 driver's implicit transactions make SAVEPOINT unreliable, so on SQLite
    (single-user development) this is a no-op and a lost race surfaces as the usual 409."""
    from contextlib import nullcontext

    return nullcontext() if db.get_bind().dialect.name == "sqlite" else db.begin_nested()


def include_object(obj, name, type_, reflected, compare_to):
    """For migration autogenerate: full-text search indexes are PostgreSQL-only expression indexes written by hand in
    migration 0006 (not described in the models), so they are not schema drift."""
    return not (type_ == "index" and reflected and compare_to is None and (name or "").endswith("_fts"))
