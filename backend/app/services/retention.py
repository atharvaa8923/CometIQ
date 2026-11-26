"""Data retention: delete operational data that is no longer needed, on a daily schedule.

Every rule is configurable (0 = keep forever) and the run reports what it removed. Nothing that is evidence for a report,
a decision or an application is deleted: postings with applications or in a documented job sample are kept, and job-sample
snapshots stay while any report uses them.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import (AiUsage, Application, AuditLog, CacheVersion, GapAnalysis, IdempotencyKey, Job, JobSample, Notification, PasswordReset,
                      SyncRun, Task)
from .sync import SYNCED_SOURCES

log = logging.getLogger("cometiq.retention")


def _ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def run(db: Session, dry_run: bool = False) -> dict[str, int]:
    s = get_settings()
    out: dict[str, int] = {}

    def apply(name: str, stmt) -> None:
        if dry_run:
            out[name] = len(db.execute(select(stmt.table.c[list(stmt.table.primary_key.columns)[0].name]).where(stmt.whereclause)).all())
        else:
            out[name] = db.execute(stmt).rowcount or 0

    if s.RETENTION_TASKS_DAYS:
        apply("finished_tasks", delete(Task).where(Task.status.in_(("done", "failed")), Task.created_at < _ago(s.RETENTION_TASKS_DAYS)))
    if s.RETENTION_NOTIFICATIONS_DAYS:
        apply("read_notifications", delete(Notification).where(Notification.read_at.is_not(None),
                                                               Notification.created_at < _ago(s.RETENTION_NOTIFICATIONS_DAYS)))
        apply("old_unread_notifications", delete(Notification).where(Notification.created_at < _ago(2 * s.RETENTION_NOTIFICATIONS_DAYS)))
    apply("used_or_expired_password_resets", delete(PasswordReset).where(
        (PasswordReset.used_at.is_not(None)) | (PasswordReset.expires_at < _ago(1))))
    if s.RETENTION_IDEMPOTENCY_HOURS:
        apply("idempotency_keys", delete(IdempotencyKey).where(
            IdempotencyKey.created_at < datetime.now(timezone.utc) - timedelta(hours=s.RETENTION_IDEMPOTENCY_HOURS)))
    if s.RETENTION_AI_USAGE_DAYS:
        cutoff = _ago(s.RETENTION_AI_USAGE_DAYS).date().isoformat()
        apply("ai_usage_days", delete(AiUsage).where(AiUsage.day < cutoff))
    if s.RETENTION_AUDIT_DAYS:
        apply("audit_log", delete(AuditLog).where(AuditLog.created_at < _ago(s.RETENTION_AUDIT_DAYS)))
    if s.RETENTION_SYNC_RUNS_DAYS:
        apply("sync_runs", delete(SyncRun).where(SyncRun.started_at < _ago(s.RETENTION_SYNC_RUNS_DAYS)))
    if s.RETENTION_CLOSED_JOBS_DAYS:
        keep = {jid for ids in db.scalars(select(JobSample.job_ids).where(JobSample.kind == "documented")) for jid in (ids or [])}
        with_apps = select(Application.job_id)
        candidates = [jid for jid in db.scalars(select(Job.id).where(
            ~Job.is_open, Job.source.in_(SYNCED_SOURCES), Job.posted_at < _ago(s.RETENTION_CLOSED_JOBS_DAYS), Job.id.not_in(with_apps)))
            if jid not in keep]
        out["closed_synced_postings"] = len(candidates)
        if candidates and not dry_run:
            for i in range(0, len(candidates), 500):
                db.execute(delete(Job).where(Job.id.in_(candidates[i:i + 500])))
    if s.RETENTION_UNUSED_SNAPSHOTS_DAYS:
        used = select(GapAnalysis.sample_id).where(GapAnalysis.sample_id.is_not(None))
        apply("unused_job_snapshots", delete(JobSample).where(JobSample.kind == "auto", JobSample.id.not_in(used),
                                                              JobSample.created_at < _ago(s.RETENTION_UNUSED_SNAPSHOTS_DAYS)))
    apply("old_retention_locks", delete(CacheVersion).where(CacheVersion.scope.like("lock:retention:%"),
                                                            CacheVersion.scope < f"lock:retention:{_ago(30).date().isoformat()}"))
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return out


def _daily_tick() -> dict | None:
    """Run once per day across all app instances: the first instance to insert today's lock row does the work."""
    key = f"lock:retention:{datetime.now(timezone.utc).date().isoformat()}"
    with SessionLocal() as db:
        db.add(CacheVersion(scope=key, version=0))
        try:
            db.commit()
        except IntegrityError:
            return None
        result = run(db)
        log.info("Retention run removed: %s", {k: v for k, v in result.items() if v})
        return result


async def scheduler_loop(interval_s: int = 3600) -> None:
    while True:
        try:
            await asyncio.to_thread(_daily_tick)
        except Exception:
            log.exception("Retention run failed")
        await asyncio.sleep(interval_s)
