"""Job-market sync: pulls postings from every configured source, nightly and on demand.

- GitHub new-grad/internship lists: always on (free).
- Adzuna: when ADZUNA_APP_ID/ADZUNA_APP_KEY are set.
- USAJobs: when USAJOBS_API_KEY/USAJOBS_EMAIL are set.
Postings from synced sources older than JOB_EXPIRE_DAYS are closed so demand reflects the current market.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Job, SyncRun
from . import jobs as jobsvc
from . import sources

log = logging.getLogger("cometiq.sync")
# One search query per business-relevant role family keeps API usage modest (~10 calls per source).
QUERIES = ["data analyst", "business analyst", "financial analyst", "data scientist", "supply chain analyst",
           "marketing analyst", "accountant", "cybersecurity analyst", "product manager", "management consultant"]
SYNCED_SOURCES = ("github", "adzuna", "usajobs")


def configured_sources() -> dict[str, dict]:
    s = get_settings()
    return {
        "github": {"enabled": True, "detail": "SimplifyJobs new-grad & internship lists (free, US roles)"},
        "adzuna": {"enabled": bool(s.ADZUNA_APP_ID and s.ADZUNA_APP_KEY), "detail": "Adzuna API — set ADZUNA_APP_ID and ADZUNA_APP_KEY"},
        "usajobs": {"enabled": bool(s.USAJOBS_API_KEY and s.USAJOBS_EMAIL), "detail": "USAJobs API — set USAJOBS_API_KEY and USAJOBS_EMAIL"},
    }


def _fetch(source: str) -> list[dict]:
    s = get_settings()
    if source == "github":
        rows = []
        for name, url in sources.GITHUB_LISTS.items():
            rows += sources.fetch_github_list(name, url, limit=150)
        return rows
    fetch = sources.fetch_adzuna if source == "adzuna" else sources.fetch_usajobs
    rows = []
    for q in QUERIES:
        rows += fetch(q, s.JOB_SYNC_LOCATION) if source == "adzuna" else fetch(q, s.JOB_SYNC_LOCATION, s.JOB_SYNC_PER_QUERY)
    return rows


def expire_old(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().JOB_EXPIRE_DAYS)
    res = db.execute(update(Job).where(Job.is_open, Job.source.in_(SYNCED_SOURCES), Job.posted_at < cutoff).values(is_open=False))
    return res.rowcount or 0


def run_sync(db: Session, run: SyncRun) -> SyncRun:
    results, failures, enabled = {}, 0, 0
    for name, cfg in configured_sources().items():
        if not cfg["enabled"]:
            results[name] = {"skipped": True}
            continue
        enabled += 1
        try:
            rows = _fetch(name)
            added = sum(1 for r in rows if jobsvc.upsert_job(db, r))
            db.commit()
            results[name] = {"fetched": len(rows), "added": added}
        except Exception as e:  # keep going with other sources
            db.rollback()
            failures += 1
            results[name] = {"error": f"{type(e).__name__}: {e}"[:300]}
            log.warning("Job sync source %s failed: %s", name, e)
    results["expired"] = expire_old(db)
    run.results = results
    run.status = "ok" if failures == 0 else ("failed" if failures == enabled else "partial")
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    log.info("Job sync %s finished: %s", run.trigger, results)
    return run


def start_run(db: Session, trigger: str, run_key: str | None = None) -> SyncRun | None:
    """Create the run row. For nightly runs the unique run_key acts as a cross-process lock."""
    run = SyncRun(trigger=trigger, run_key=run_key)
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return run


def nightly_due(now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    return f"nightly-{now:%Y-%m-%d}" if now.hour >= get_settings().JOB_SYNC_HOUR_UTC else None


def _nightly_tick() -> None:
    with SessionLocal() as db:
        # First start of a fresh deployment: fill the market right away instead of waiting for tonight.
        if not db.scalar(select(Job.id).where(Job.is_open).limit(1)):
            run = start_run(db, "initial", "initial-bootstrap")
            if run:
                run_sync(db, run)
                return
    key = nightly_due()
    if not key:
        return
    with SessionLocal() as db:
        if db.scalar(select(SyncRun.id).where(SyncRun.run_key == key)):
            return
        run = start_run(db, "nightly", key)
        if run:
            run_sync(db, run)


async def scheduler_loop(interval_s: int = 600) -> None:
    """Background loop started with the app; checks every 10 minutes whether tonight's sync is due."""
    while True:
        try:
            await asyncio.to_thread(_nightly_tick)
        except Exception:
            log.exception("Nightly job sync failed")
        await asyncio.sleep(interval_s)
