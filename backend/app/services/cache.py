"""Read cache for heavy views (scorecard, curriculum map, knowledge graph, candidate ranking, dashboards).

Cache keys include a version number per organization (and a shared "*" version for job postings), stored in the
cache_versions table. Every committed change to cacheable data bumps the version, so a cached view is never served after
the data it was built from changed, on any app instance. The bump runs in its own short transaction right after commit,
so it never holds a lock while a request is still running. The store itself is a small in-process LRU with a TTL.
"""
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, engine
from ..models import AiUsage, AuditLog, CacheVersion, IdempotencyKey, LtiNonce, Notification, PasswordReset, SyncRun, Task

IGNORED = (Task, AuditLog, Notification, AiUsage, CacheVersion, PasswordReset, SyncRun, IdempotencyKey, LtiNonce)
_lock = threading.Lock()
_store: "OrderedDict[tuple, tuple[float, Any]]" = OrderedDict()
MAX_ENTRIES = 512
stats = {"hits": 0, "misses": 0}


def _scope_of(obj, fallback: str | None) -> str:
    org = getattr(obj, "org_id", None)
    if org:
        return org
    if hasattr(obj, "org_id"):  # an explicit NULL org (shared job postings)
        return "*"
    return fallback or "*"


@event.listens_for(Session, "after_flush")
def _track(session, _ctx):
    from .tasks import current_org

    changed = [o for o in (*session.new, *session.dirty, *session.deleted) if not isinstance(o, IGNORED)]
    if changed:
        org = current_org.get()
        session.info.setdefault("cache_scopes", set()).update(_scope_of(o, org) for o in changed)


@event.listens_for(Session, "do_orm_execute")
def _track_bulk(state):
    # bulk UPDATE / DELETE statements (retention, erasure, job expiry) touch rows without loading them: invalidate broadly
    if state.is_update or state.is_delete:
        table = getattr(state.statement, "table", None)
        if table is None or table.name not in {c.__tablename__ for c in IGNORED}:
            state.session.info.setdefault("cache_scopes", set()).add("*")


@event.listens_for(Session, "after_commit")
def _bump(session):
    scopes = session.info.pop("cache_scopes", None)
    if scopes:
        bump(scopes)


@event.listens_for(Session, "after_rollback")
def _forget(session):
    session.info.pop("cache_scopes", None)


def bump(scopes) -> None:
    with engine.begin() as conn:
        for s in sorted(scopes):
            conn.execute(text("INSERT INTO cache_versions (scope, version) VALUES (:s, 1) "
                              "ON CONFLICT (scope) DO UPDATE SET version = cache_versions.version + 1"), {"s": s})


def versions(db: Session, org_id: str) -> tuple[int, int]:
    rows = dict(db.execute(select(CacheVersion.scope, CacheVersion.version).where(CacheVersion.scope.in_((org_id, "*")))).all())
    return rows.get(org_id, 0), rows.get("*", 0)


def cached(db: Session, org_id: str, key: tuple, compute: Callable[[], Any], ttl: int | None = None) -> Any:
    if not get_settings().CACHE_ENABLED:
        return compute()
    full = (org_id, *key, versions(db, org_id))
    now = time.monotonic()
    with _lock:
        hit = _store.get(full)
        if hit and hit[0] > now:
            _store.move_to_end(full)
            stats["hits"] += 1
            return hit[1]
    value = compute()
    with _lock:
        stats["misses"] += 1
        _store[full] = (now + (ttl or get_settings().CACHE_TTL_S), value)
        _store.move_to_end(full)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
    return value


def clear() -> None:
    with _lock:
        _store.clear()


__all__ = ["cached", "bump", "versions", "clear", "stats", "SessionLocal"]
