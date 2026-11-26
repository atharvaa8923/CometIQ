"""Database-backed background task queue.

Tasks survive restarts, are claimed atomically (safe with several app instances), retried for
transient kinds (email), and report progress so the UI can show it. Handlers register by kind.
"""
import contextvars
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Task

log = logging.getLogger("cometiq.tasks")
HANDLERS: dict[str, Callable[[Session, Task], dict | None]] = {}
RETRYABLE = {"email.send": 3, "credentials.revoke": 5}   # attempts for tasks that call outside services
current_org: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_org", default=None)
_stop = threading.Event()


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


class TaskError(Exception):
    """A failure to show the person as written (e.g. "Connect Canvas again"), not a crash."""


def enqueue(db: Session, kind: str, payload: dict, org_id: str | None = None, user_id: str | None = None) -> Task:
    """Persist a task (commits). With TASKS_INLINE it runs immediately in this thread."""
    t = Task(kind=kind, payload=payload, org_id=org_id, user_id=user_id)
    db.add(t)
    db.commit()
    if get_settings().TASKS_INLINE:
        load_handlers()
        _claim_and_run(t.id)
        db.refresh(t)
    return t


def set_progress(db: Session, task: Task, text: str) -> None:
    task.progress = text[:200]
    db.commit()


def _claim_and_run(task_id: str, already_claimed: bool = False) -> bool:
    with SessionLocal() as db:
        if not already_claimed:
            # compare-and-set: only one worker (on any instance) can move a task from queued to running
            claimed = db.execute(update(Task).where(Task.id == task_id, Task.status == "queued")
                                 .values(status="running", started_at=datetime.now(timezone.utc), attempts=Task.attempts + 1)).rowcount
            db.commit()
            if not claimed:
                return False
        task = db.get(Task, task_id)
        token = current_org.set(task.org_id)
        try:
            fn = HANDLERS.get(task.kind)
            if not fn:
                raise RuntimeError(f"No handler for task kind {task.kind}")
            task.result = fn(db, task) or {}
            task.status, task.progress = "done", None
        except Exception as e:  # never crash the worker
            db.rollback()
            task = db.get(Task, task_id)
            retry = task.attempts < RETRYABLE.get(task.kind, 1)
            task.status = "queued" if retry else "failed"
            task.error = f"{type(e).__name__}: {e}"[:2000]   # "TaskError: …" is shown to the person; anything else is not
            log.warning("Task %s (%s) %s: %s", task.id, task.kind, "will retry" if retry else "failed", e)
        finally:
            current_org.reset(token)
        task.finished_at = datetime.now(timezone.utc) if task.status in ("done", "failed") else None
        db.commit()
        return True


def _next_queued() -> str | None:
    with SessionLocal() as db:
        return db.scalar(select(Task.id).where(Task.status == "queued").order_by(Task.created_at).limit(1))


def _claim_next_pg() -> str | None:
    """PostgreSQL: claim the oldest queued task no other worker is claiming, in one statement (FOR UPDATE SKIP LOCKED)."""
    from sqlalchemy import text

    with SessionLocal() as db:
        tid = db.execute(text(
            "UPDATE tasks SET status = 'running', started_at = now(), attempts = attempts + 1 "
            "WHERE id = (SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
            "RETURNING id")).scalar()
        db.commit()
        return tid


MAX_STALE_REQUEUES = 3


def requeue_stale(minutes: int = 15) -> int:
    """Tasks left 'running' by a crashed/restarted instance go back to the queue."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with SessionLocal() as db:
        # a task whose worker keeps dying (e.g. it crashes the process) must not loop forever
        db.execute(update(Task).where(Task.status == "running", Task.started_at < cutoff, Task.attempts >= MAX_STALE_REQUEUES)
                   .values(status="failed", error="Stopped: the worker running it stopped repeatedly", finished_at=datetime.now(timezone.utc)))
        n = db.execute(update(Task).where(Task.status == "running", Task.started_at < cutoff).values(status="queued")).rowcount
        db.commit()
        return n or 0


def _worker_loop(idx: int) -> None:
    log.info("Task worker %d started", idx)
    while not _stop.is_set():
        try:
            if SessionLocal.kw["bind"].dialect.name == "postgresql":
                tid = _claim_next_pg()
                if tid:
                    _claim_and_run(tid, already_claimed=True)
                    continue
            else:
                tid = _next_queued()
                if tid:
                    _claim_and_run(tid)
                    continue
        except Exception:
            log.exception("Task worker error")
        _stop.wait(1.0)


def load_handlers() -> None:
    import importlib

    importlib.import_module("app.services.task_handlers")  # registers @handler functions


def start_workers() -> list[threading.Thread]:
    load_handlers()
    _stop.clear()
    requeue_stale()
    threads = [threading.Thread(target=_worker_loop, args=(i,), daemon=True, name=f"cometiq-worker-{i}")
               for i in range(max(get_settings().TASK_WORKERS, 0))]
    for t in threads:
        t.start()
    return threads


def stop_workers() -> None:
    _stop.set()


def wait_for(task_id: str, timeout: float = 30) -> Task:
    """Test helper: block until a task finishes."""
    end = time.time() + timeout
    while time.time() < end:
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t and t.status in ("done", "failed"):
                return t
        time.sleep(0.1)
    raise TimeoutError(task_id)
