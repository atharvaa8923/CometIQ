"""CometIQ — one app: REST API under /api and the React frontend at /."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import admin, auth, catalog, dashboard, forge, gap, jobs, path
from .seed import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="CometIQ API", version="1.0.0", lifespan=lifespan,
              description="AI Intelligence for Education, Skills & Talent")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, admin.router, catalog.router, dashboard.router, gap.router, jobs.router, forge.router, path.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# ── Serve the built React app (single deployable) ──────────────────────────────
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str = ""):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    f = FRONTEND / path
    if path and f.is_file() and FRONTEND in f.resolve().parents:
        return FileResponse(f)
    index = FRONTEND / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm install && npm run build"}, status_code=503)
