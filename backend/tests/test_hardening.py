"""Hardening: one error format everywhere, safe concurrent and duplicate submissions, per-user rate limits."""
import io
import threading

from sqlalchemy import func, select

SYL = """BUAN 6390 Analytics Practicum
LEARNING OBJECTIVES
1. Write SQL queries for business questions.
Week 1: SQL review
Week 2: Dashboards in Tableau
"""


def _course(client, fac, code="BUAN 6390"):
    up = client.post("/api/gap/syllabi", headers=fac, data={"title": "Analytics Practicum", "code": code, "semester": "Spring 2026",
                                                            "target": "Data Analyst"}, files={"file": ("s.txt", io.BytesIO(SYL.encode()), "text/plain")}).json()
    a = client.get(f"/api/gap/analyses/{up['analysis_id']}", headers=fac).json()
    gap = next(s for s in a["skills"] if s["status"] == "missing")
    client.put(f"/api/gap/analyses/{a['id']}/reviews/{gap['skill_id']}", headers=fac, json={"faculty_status": "not_covered"})
    return up["syllabus_id"], a["id"], gap["skill_id"]


def _envelope(r, status, code):
    j = r.json()
    assert r.status_code == status, r.text
    assert j["error"]["status"] == status and j["error"]["code"] == code
    assert j["detail"] == j["error"]["message"] and j["request_id"]
    return j


# ── Uniform errors ─────────────────────────────────────────────────────────────
def test_every_error_uses_the_same_format(client, tokens):
    fac = tokens["faculty"]
    _envelope(client.get("/api/gap/analyses/does-not-exist", headers=fac), 404, "not_found")
    _envelope(client.get("/api/gap/analyses/x"), 401, "unauthorized")
    _envelope(client.get("/api/admin/users", headers=tokens["student"]), 403, "forbidden")
    j = _envelope(client.post("/api/auth/login", json={"email": "admin@cometiq.app"}), 422, "validation_error")
    assert j["error"]["fields"] == [{"field": "password", "message": "Field required"}] and "password" in j["detail"]
    _envelope(client.get("/api/search?q=a", headers=fac), 400, "bad_request")
    _envelope(client.get("/api/no-such-endpoint", headers=fac), 404, "not_found")


# ── Concurrency ────────────────────────────────────────────────────────────────
def test_two_people_deciding_at_once_leave_one_active_decision(client, tokens):
    from app.db import SessionLocal
    from app.models import GapAnalysis, GapDecision, Syllabus, User
    from app.services import decisions

    sid, aid, skill = _course(client, tokens["faculty"])
    barrier, outcomes = threading.Barrier(4), []

    def decide(i):
        with SessionLocal() as db:
            ga, syl = db.get(GapAnalysis, aid), db.get(Syllabus, sid)
            user = db.scalar(select(User).where(User.email == "faculty@cometiq.app"))
            barrier.wait()
            try:
                decisions.record(db, user, syl, ga, skill, "defer", f"Reviewer {i}: revisit with the program review.", None, "Fall 2027")
                db.commit()
                outcomes.append("saved")
            except Exception as e:   # lost the race: unique index (IntegrityError) or a lock wait (OperationalError)
                db.rollback()
                outcomes.append(type(e).__name__)

    threads = [threading.Thread(target=decide, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert "saved" in outcomes and set(outcomes) <= {"saved", "IntegrityError", "OperationalError"}, outcomes
    with SessionLocal() as db:
        active = db.scalar(select(func.count()).select_from(GapDecision).where(
            GapDecision.syllabus_id == sid, GapDecision.skill_id == skill, GapDecision.status.in_(decisions.ACTIVE)))
        assert active == 1
        # every superseded decision points at a decision that exists
        rows = list(db.scalars(select(GapDecision).where(GapDecision.syllabus_id == sid, GapDecision.skill_id == skill)))
        ids = {d.id for d in rows}
        assert all(d.superseded_by in ids for d in rows if d.status == "superseded")


def test_double_submit_with_idempotency_key_acts_once(client, tokens):
    fac = tokens["faculty"]
    sid, aid, skill = _course(client, fac, "BUAN 6391")
    body = {"decision": "out_of_scope", "rationale": "Covered by the capstone instead of here."}
    h = {**fac, "Idempotency-Key": "test-double-click-1"}
    r1 = client.put(f"/api/gap/analyses/{aid}/decisions/{skill}", headers=h, json=body)
    r2 = client.put(f"/api/gap/analyses/{aid}/decisions/{skill}", headers=h, json=body)
    assert r1.status_code == r2.status_code == 200
    assert r2.headers.get("Idempotent-Replayed") == "true" and r2.json() == r1.json()
    d = client.get(f"/api/gap/syllabi/{sid}/decisions", headers=fac).json()
    assert len(d["active"]) == 1 and not d["history"]          # acted once
    _envelope(client.put(f"/api/gap/analyses/{aid}/decisions/{skill + 1}", headers=h, json=body), 422, "idempotency_key_reused")
    # a different user's identical key is a different request
    r3 = client.put(f"/api/gap/analyses/{aid}/decisions/{skill}", headers={**tokens["admin"], "Idempotency-Key": "test-double-click-1"}, json=body)
    assert "Idempotent-Replayed" not in r3.headers


def test_retry_while_first_request_is_running_gets_409(client, tokens):
    import hashlib

    import jwt as pyjwt

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import IdempotencyKey

    fac = tokens["faculty"]
    uid = pyjwt.decode(fac["Authorization"][7:], get_settings().JWT_SECRET, algorithms=["HS256"])["sub"]
    with SessionLocal() as db:   # a first attempt that is still running
        db.add(IdempotencyKey(key=hashlib.sha256(f"{uid}:slow-1".encode()).hexdigest(), user_id=uid, method="POST",
                              path="/api/notifications/read-all", status="pending"))
        db.commit()
    r = client.post("/api/notifications/read-all", headers={**fac, "Idempotency-Key": "slow-1"})
    _envelope(r, 409, "in_progress")
    assert r.headers["Retry-After"] == "2"


# ── Rate limits ────────────────────────────────────────────────────────────────
def test_expensive_endpoints_are_rate_limited_per_user(client, tokens, monkeypatch):
    from app import limits
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "RATE_LIMIT_MULTIPLIER", 2 / 120)   # search: 120/min → 2/min
    limits.window.reset()
    try:
        emp, adv = tokens["employer"], tokens["advisor"]
        assert [client.get("/api/search?q=python", headers=emp).status_code for _ in range(2)] == [200, 200]
        r = client.get("/api/search?q=python", headers=emp)
        _envelope(r, 429, "rate_limited")
        assert 1 <= int(r.headers["Retry-After"]) <= 61 and r.headers["X-RateLimit-Limit"] == "2"
        assert client.get("/api/search?q=python", headers=adv).status_code == 200      # budgets are per user
        assert client.get("/api/notifications/summary", headers=emp).status_code != 429   # cheap endpoints are not limited
    finally:
        limits.window.reset()


def test_sliding_window_frees_up_after_a_minute():
    from app.limits import SlidingWindow

    w = SlidingWindow()
    assert [w.hit("u", "r", 3, now=t) for t in (0, 1, 2)] == [0, 0, 0]
    assert w.hit("u", "r", 3, now=3) == 57.0   # until the hit at t=0 leaves the window
    assert w.hit("u", "r", 3, now=60.5) == 0      # the first hit left the window
