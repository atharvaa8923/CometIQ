"""CometIQ — one app: REST API under /api and the React frontend at /."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import errors, limits, monitoring
from .config import get_settings
from .routers import admin, ask, auth, badges, canvas, search, catalog, curriculum, dashboard, partners, evidence, forge, gap, graphmap, jobs, match, notifications, path, privacy, tasks
from .seed import init_db

settings = get_settings()
monitoring.setup_logging()
monitoring.setup_sentry()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.ENV == "production" and (settings.JWT_SECRET == "change-me-in-production" or len(settings.JWT_SECRET) < 32):
        raise RuntimeError("Set a strong JWT_SECRET (32+ characters) before running in production")
    init_db()
    from .services import cache

    cache.clear()  # registers the invalidation hooks; start each process with an empty cache
    from .services import tasks as tasksvc

    if not settings.TASKS_INLINE:
        tasksvc.start_workers()
    task = None
    if settings.JOB_SYNC_ENABLED:
        from .services.sync import scheduler_loop

        task = asyncio.create_task(scheduler_loop())
    retention = None
    if settings.RETENTION_ENABLED:
        from .services.retention import scheduler_loop as retention_loop

        retention = asyncio.create_task(retention_loop())
    yield
    if task:
        task.cancel()
    if retention:
        retention.cancel()
    tasksvc.stop_workers()


app = FastAPI(title="CometIQ API", version="1.0.0", lifespan=lifespan,
              description="AI Intelligence for Education, Skills & Talent")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.middleware("http")(limits.idempotency_middleware)
app.middleware("http")(limits.rate_limit_middleware)
app.middleware("http")(monitoring.request_id_middleware)
errors.install(app)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.ENV == "production":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


for r in (auth.router, admin.router, catalog.router, dashboard.router, gap.router, jobs.router, forge.router, path.router, path.advising, match.router, evidence.router, graphmap.router, notifications.router, tasks.router, privacy.router,
          curriculum.router, badges.router, badges.public, partners.router, ask.router, search.router, canvas.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    """Liveness: the process is up (cheap; used by the load balancer)."""
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/api/health/ready")
def ready():
    """Readiness: database reachable, task queue and job sync status (for uptime monitors)."""
    ok, checks = monitoring.readiness()
    return JSONResponse({"status": "ok" if ok else "degraded", **checks}, status_code=200 if ok else 503)


_client_errors: dict[str, list[float]] = {}


@app.post("/api/client-errors", status_code=204)
async def client_error(request: Request):
    """Browser JavaScript errors (rate-limited, size-capped, no personal data expected)."""
    import time as _t

    ip = request.client.host if request.client else "?"
    recent = [t for t in _client_errors.get(ip, []) if _t.time() - t < 60]
    if len(recent) >= 10:
        return Response(status_code=204)
    _client_errors[ip] = recent + [_t.time()]
    body = (await request.body())[:4000].decode("utf-8", "replace")
    logging.getLogger("cometiq.client").warning("Browser error: %s", body)
    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.capture_message(f"Browser error: {body[:500]}", level="warning")
    return Response(status_code=204)


# ── Serve the built React app (single deployable) ──────────────────────────────
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str = ""):
    if path.startswith("api/"):
        return errors.respond(404, "No such API endpoint")
    f = FRONTEND / path
    if path and f.is_file() and FRONTEND in f.resolve().parents:
        return FileResponse(f)
    index = FRONTEND / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm install && npm run build"}, status_code=503)
