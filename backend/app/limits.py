"""Request guards that apply across endpoints.

Idempotency keys: a write request (POST/PUT/PATCH/DELETE) may send `Idempotency-Key: <random>`; the frontend sends one
per submission. If the same user sends the same key again (a double click, a network retry), the stored first response
is returned instead of acting twice; while the first is still running the retry gets 409. Keys live for a day.

Rate limits: expensive endpoints have a per-user budget per minute (AI calls, simulations, rankings, exports). Over it,
the response is 429 in the standard error format with Retry-After. Counters are in process memory, so with several app
instances each enforces its own budget; behind a load balancer use sticky sessions or move the counters to Redis.
"""
import asyncio
import hashlib
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request
from fastapi.responses import Response
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import SessionLocal
from .errors import respond
from .models import IdempotencyKey

WRITE = {"POST", "PUT", "PATCH", "DELETE"}
PENDING_STALE_S = 300
MAX_STORED_BODY = 1_000_000


def _subject(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(auth[7:], get_settings().JWT_SECRET, algorithms=["HS256"]).get("sub")
    except jwt.PyJWTError:
        return None


# ── Idempotency ────────────────────────────────────────────────────────────────
def _claim(full: str, user_id: str, method: str, path: str):
    """Returns None if this request owns the key, else the existing row (detached)."""
    with SessionLocal() as db:
        db.add(IdempotencyKey(key=full, user_id=user_id, method=method, path=path, status="pending"))
        try:
            db.commit()
            return None
        except IntegrityError:
            db.rollback()
        row = db.get(IdempotencyKey, full)
        if row is None:  # removed between the two statements: try once more
            db.add(IdempotencyKey(key=full, user_id=user_id, method=method, path=path, status="pending"))
            try:
                db.commit()
                return None
            except IntegrityError:
                db.rollback()
                row = db.get(IdempotencyKey, full)
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        if row.status == "pending" and datetime.now(timezone.utc) - created > timedelta(seconds=PENDING_STALE_S):
            row.created_at = datetime.now(timezone.utc)   # the first attempt died mid-request: take it over
            db.commit()
            return None
        db.expunge(row)
        return row


def _finish(full: str, status: int, body: bytes, media: str | None) -> None:
    with SessionLocal() as db:
        if status >= 500 or len(body) > MAX_STORED_BODY:
            db.execute(delete(IdempotencyKey).where(IdempotencyKey.key == full))   # allow a retry
        else:
            row = db.get(IdempotencyKey, full)
            if row:
                row.status, row.response_status, row.response_body, row.response_type = "done", status, body, media
        db.commit()


async def idempotency_middleware(request: Request, call_next):
    key = request.headers.get("idempotency-key", "").strip()
    if request.method not in WRITE or not key or not request.url.path.startswith("/api/"):
        return await call_next(request)
    if len(key) > 100 or not re.fullmatch(r"[A-Za-z0-9_\-:.]+", key):
        return respond(400, "Idempotency-Key must be up to 100 letters, digits or - _ : .")
    user_id = _subject(request)
    if not user_id:
        return await call_next(request)   # unauthenticated requests are not deduplicated
    full = hashlib.sha256(f"{user_id}:{key}".encode()).hexdigest()
    path = request.url.path[:300]
    existing = await asyncio.to_thread(_claim, full, user_id, request.method, path)
    if existing is not None:
        if existing.method != request.method or existing.path != path:
            return respond(422, "This Idempotency-Key was already used for a different request", code="idempotency_key_reused")
        if existing.status == "pending":
            return respond(409, "This request is already being processed. Wait a moment, then refresh.", code="in_progress",
                           headers={"Retry-After": "2"})
        return Response(existing.response_body or b"", status_code=existing.response_status or 200,
                        media_type=existing.response_type, headers={"Idempotent-Replayed": "true"})
    try:
        resp = await call_next(request)
    except Exception:
        await asyncio.to_thread(_finish, full, 500, b"", None)
        raise
    body = b"".join([chunk async for chunk in resp.body_iterator])
    await asyncio.to_thread(_finish, full, resp.status_code, body, resp.headers.get("content-type"))
    headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
    return Response(body, status_code=resp.status_code, headers=headers)


# ── Rate limits ────────────────────────────────────────────────────────────────
# (name, method, path pattern, requests per minute per user)
RULES: list[tuple[str, str, re.Pattern, int]] = [(n, m, re.compile(p), r) for n, m, p, r in (
    ("ask", "POST", r"^/api/ask$", 20),
    ("copilot", "POST", r"^/api/gap/copilot/preview$", 30),
    ("analyze", "POST", r"^/api/gap/syllabi/[^/]+/analyze$", 20),
    ("generate", "POST", r"^/api/forge/drafts$", 10),
    ("explain", "POST", r"^/api/match/employer/jobs/[^/]+/candidates/[^/]+/explain$", 20),
    ("simulate", "POST", r"^/api/curriculum/programs/[^/]+/simulate$", 30),
    ("what_if", "POST", r"^/api/path/what-if$", 60),
    ("scorecard", "GET", r"^/api/curriculum/scorecard$", 60),
    ("program_map", "GET", r"^/api/curriculum/programs/[^/]+/map$", 60),
    ("candidates", "GET", r"^/api/(match/employer/jobs|partners/projects)/[^/]+/candidates$", 60),
    ("talent", "GET", r"^/api/match/employer/talent$", 60),
    ("graph", "GET", r"^/api/graph/map$", 60),
    ("search", "GET", r"^/api/search$", 120),
    ("exports", "GET", r"\.(pdf|xlsx|docx|csv)$", 30),
)]
WINDOW_S = 60.0


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def hit(self, who: str, rule: str, limit: int, now: float | None = None) -> float:
        """Record a request; returns 0 if allowed, else seconds until the next one is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault((who, rule), deque())
            while q and now - q[0] >= WINDOW_S:
                q.popleft()
            if len(q) >= limit:
                return max(0.1, WINDOW_S - (now - q[0]))
            q.append(now)
            if len(self._hits) > 50_000:   # drop idle counters
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= WINDOW_S]:
                    del self._hits[k]
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


window = SlidingWindow()


def rule_for(method: str, path: str):
    for name, m, pat, limit in RULES:
        if m == method and pat.search(path):
            return name, limit
    return None


async def rate_limit_middleware(request: Request, call_next):
    s = get_settings()
    rule = rule_for(request.method, request.url.path) if s.RATE_LIMITS_ENABLED else None
    if rule is None:
        return await call_next(request)
    name, limit = rule
    limit = max(1, int(limit * s.RATE_LIMIT_MULTIPLIER))
    who = _subject(request) or f"ip:{request.client.host if request.client else '?'}"
    wait = window.hit(who, name, limit)
    if wait:
        secs = int(wait) + 1
        return respond(429, f"Too many requests for this feature (limit {limit} per minute). Try again in {secs} seconds.",
                       headers={"Retry-After": str(secs), "X-RateLimit-Limit": str(limit)})
    return await call_next(request)
