"""Monitoring: request IDs, structured logging, optional Sentry, readiness checks."""
import json
import logging
import time
import uuid
from contextvars import ContextVar

from .config import get_settings

request_id: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("cometiq.http")


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, r):
        out = {"ts": self.formatTime(r, "%Y-%m-%dT%H:%M:%S"), "level": r.levelname, "logger": r.name,
               "msg": r.getMessage(), "request_id": getattr(r, "request_id", "-")}
        if r.exc_info:
            out["exc"] = self.formatException(r.exc_info)
        return json.dumps(out)


def setup_logging() -> None:
    s = get_settings()
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(_JsonFormatter() if s.LOG_FORMAT == "json"
                         else logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def _scrub(event, _hint):
    """Never send personal data to Sentry: drop request bodies, cookies, auth headers and user info."""
    req = event.get("request") or {}
    req.pop("data", None)
    req.pop("cookies", None)
    headers = req.get("headers") or {}
    for h in list(headers):
        if h.lower() in ("authorization", "cookie", "x-api-key"):
            headers[h] = "[removed]"
    event.pop("user", None)
    return event


def setup_sentry() -> bool:
    s = get_settings()
    if not s.SENTRY_DSN:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=s.SENTRY_DSN, environment=s.ENV, traces_sample_rate=s.SENTRY_TRACES_SAMPLE_RATE,
                    send_default_pii=False, before_send=_scrub)
    return True


async def request_id_middleware(request, call_next):
    rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
    token = request_id.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Log with the request id, report to Sentry (if configured) and return a safe message with a reference.
        logging.getLogger("cometiq").exception("Unhandled error on %s %s", request.method, request.url.path)
        if get_settings().SENTRY_DSN:
            import sentry_sdk

            sentry_sdk.capture_exception()
        from .errors import respond

        response = respond(500, "Something went wrong on our side. Please try again.")
    finally:
        request_id.reset(token)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = rid
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        request_id.set(rid)
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, ms)
        request_id.set("-")
    return response


def readiness() -> tuple[bool, dict]:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select, text

    from .db import SessionLocal
    from .models import SyncRun, Task
    from .services import ai, email, nebula

    checks: dict = {}
    ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            day = datetime.now(timezone.utc) - timedelta(hours=24)
            checks["database"] = "ok"
            checks["tasks"] = {
                "queued": db.scalar(select(func.count()).select_from(Task).where(Task.status == "queued")) or 0,
                "running": db.scalar(select(func.count()).select_from(Task).where(Task.status == "running")) or 0,
                "failed_24h": db.scalar(select(func.count()).select_from(Task).where(Task.status == "failed", Task.created_at >= day)) or 0,
            }
            from .models import User

            checks["demo_accounts"] = db.scalar(select(func.count()).select_from(User).where(User.email.like("%@cometiq.app"))) or 0
            last = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
            checks["last_job_sync"] = {"status": last.status, "at": last.started_at.isoformat()} if last else None
    except Exception as e:
        ok = False
        checks["database"] = f"error: {type(e).__name__}"
    roles = get_settings().allowed_roles()
    checks["pilot_roles"] = sorted(roles) if roles else None
    checks["integrations"] = {"claude": ai.enabled(), "nebula": nebula.enabled(), "email": email.enabled(),
                              "sentry": bool(get_settings().SENTRY_DSN)}
    return ok, checks
