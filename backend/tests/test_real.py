"""Password reset, sessions, notifications/email, background tasks and the AI usage cap."""
import re

from app.config import get_settings
from app.db import SessionLocal
from app.models import AiUsage, Task
from app.services import ai, email, tasks
from app.services.tasks import current_org

PW = "CometIQ2026!"


def _login(client, email_addr, pw=PW):
    return client.post("/api/auth/login", json={"email": email_addr, "password": pw})


def test_password_reset_flow(client):
    email.OUTBOX.clear()
    r = client.post("/api/auth/forgot-password", json={"email": "wei.chen@cometiq.app"})
    assert r.status_code == 200
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.edu"})
    assert unknown.json() == r.json()                      # no account enumeration
    msg = [m for m in email.OUTBOX if m["to"] == "wei.chen@cometiq.app"][-1]
    token = re.search(r"reset-password\?token=([\w-]+)", msg["text"]).group(1)
    old = {"Authorization": "Bearer " + _login(client, "wei.chen@cometiq.app").json()["token"]}
    assert client.post("/api/auth/reset-password", json={"token": "bogus", "password": "new-password-1"}).status_code == 400
    ok = client.post("/api/auth/reset-password", json={"token": token, "password": "new-password-1"})
    assert ok.status_code == 200 and ok.json()["token"]
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "another-pass-2"}).status_code == 400  # single use
    assert client.get("/api/auth/me", headers=old).status_code == 401                     # old sessions revoked
    assert _login(client, "wei.chen@cometiq.app", "new-password-1").status_code == 200
    assert _login(client, "wei.chen@cometiq.app").status_code == 401


def test_change_password_and_settings(client):
    tok = _login(client, "aisha.okafor@cometiq.app").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": "xxxxxxxx1"}).status_code == 400
    new = client.post("/api/auth/change-password", headers=h, json={"current_password": PW, "new_password": "brand-new-pass"}).json()["token"]
    assert client.get("/api/auth/me", headers=h).status_code == 401
    h2 = {"Authorization": f"Bearer {new}"}
    assert client.patch("/api/auth/me", headers=h2, json={"email_notifications": False}).json()["email_notifications"] is False


def test_notifications_and_emails_on_review(client, tokens):
    email.OUTBOX.clear()
    s, adv = tokens["student"], tokens["advisor"]
    client.post("/api/path/plan?save=true", headers=s)
    rv = client.post("/api/path/review", headers=s, json={"note": "check please"}).json()
    assert any(m["to"] == "advisor@cometiq.app" for m in email.OUTBOX)           # advisor told about the submission
    client.post(f"/api/advising/reviews/{rv['id']}", headers=adv, json={"decision": "approved", "note": "Great plan"})
    n = client.get("/api/notifications", headers=s).json()
    assert n["unread"] >= 1 and n["items"][0]["title"] == "Your degree plan was approved"
    assert any(m["to"] == "student@cometiq.app" and "approved" in m["subject"] for m in email.OUTBOX)
    client.post("/api/notifications/read-all", headers=s)
    assert client.get("/api/notifications", headers=s).json()["unread"] == 0


def test_task_endpoint_and_permissions(client, tokens):
    syl = client.get("/api/gap/syllabi", headers=tokens["faculty"]).json()[0]
    r = client.post(f"/api/gap/syllabi/{syl['id']}/analyze", headers=tokens["faculty"], json={"target": "Data Analyst"}).json()
    t = client.get(f"/api/tasks/{r['task_id']}", headers=tokens["faculty"]).json()
    assert t["status"] == "done" and t["result"]["analysis_id"] == r["id"]
    assert client.get(f"/api/tasks/{r['task_id']}", headers=tokens["student"]).status_code == 404


def test_failed_task_is_reported(client):
    with SessionLocal() as db:
        t = tasks.enqueue(db, "does.not.exist", {})
        assert t.status == "failed" and "No handler" in t.error


def test_worker_claims_each_task_once(client):
    """Two claims of the same queued task: only one wins (safe with several workers/instances)."""
    s = get_settings()
    with SessionLocal() as db:
        s.TASKS_INLINE = False
        try:
            t = tasks.enqueue(db, "email.send", {"to": "x@example.edu", "title": "Hi", "paragraphs": ["test"]})
        finally:
            s.TASKS_INLINE = True
    tasks.load_handlers()
    assert tasks._claim_and_run(t.id) is True
    assert tasks._claim_and_run(t.id) is False
    with SessionLocal() as db:
        assert db.get(Task, t.id).status == "done"


def test_ai_daily_cap(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(get_settings(), "AI_DAILY_LIMIT_PER_ORG", 2)
    token = current_org.set("org-cap-test")
    try:
        assert ai._within_cap() and ai._within_cap()
        assert ai._within_cap() is False                 # third call of the day is refused → built-in engine
    finally:
        current_org.reset(token)
    with SessionLocal() as db:
        db.query(AiUsage).filter(AiUsage.org_id == "org-cap-test").delete()
        db.commit()
