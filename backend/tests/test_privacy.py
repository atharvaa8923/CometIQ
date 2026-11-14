"""Consent, data export and account deletion."""
import io

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Evidence, Job, StudentProfile, User

PDF = b"%PDF-1.4\n%%EOF"


def test_register_requires_consent(client):
    body = {"full_name": "No Consent", "email": "noconsent@x.edu", "password": "password123", "role": "student", "join_code": "COMET-UTD"}
    assert client.post("/api/auth/register", json=body).status_code == 400
    r = client.post("/api/auth/register", json={**body, "accept_terms": True}).json()
    assert r["user"]["consent_version"] == client.get("/api/privacy/policy").json()["version"]


def test_export_contains_my_data_only(client, tokens):
    r = client.get("/api/privacy/export", headers=tokens["student"])
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert d["account"]["email"] == "student@cometiq.app" and "password_hash" not in d["account"]
    assert "student_profile" in d and isinstance(d["courses"], list) and isinstance(d["activity_log"], list)
    assert all(a.get("user_id") in (None, d["account"]["id"]) for a in d["activity_log"])


def _new_student(client, email):
    r = client.post("/api/auth/register", json={"full_name": "Temp Student", "email": email, "password": "password123",
                                                "role": "student", "join_code": "COMET-UTD", "accept_terms": True}).json()
    return {"Authorization": f"Bearer {r['token']}"}, r["user"]["id"]


def test_delete_my_account(client, tokens):
    h, uid = _new_student(client, "temp.delete@x.edu")
    client.post("/api/evidence", headers=h, data={"kind": "certification", "title": "Temp cert", "description": "SQL"},
                files={"file": ("c.pdf", io.BytesIO(PDF), "application/pdf")})
    job = client.get("/api/match/jobs?posted_only=true", headers=h).json()["items"][0]
    client.post(f"/api/match/jobs/{job['id']}/apply", headers=h, json={})
    assert client.post("/api/privacy/delete-account", headers=h, json={"password": "wrong", "confirm": "DELETE"}).status_code == 400
    assert client.post("/api/privacy/delete-account", headers=h, json={"password": "password123", "confirm": "nope"}).status_code == 400
    assert client.post("/api/privacy/delete-account", headers=h, json={"password": "password123", "confirm": "DELETE"}).json()["deleted"]
    assert client.get("/api/auth/me", headers=h).status_code == 401
    with SessionLocal() as db:
        assert db.get(User, uid) is None and db.get(StudentProfile, uid) is None
        assert not db.scalars(select(Evidence).where(Evidence.student_id == uid)).all()
        assert not db.scalars(select(AuditLog).where(AuditLog.user_id == uid)).all()        # audit trail anonymized
    assert client.post("/api/auth/login", json={"email": "temp.delete@x.edu", "password": "password123"}).status_code == 401


def test_admin_erasure_and_last_admin_guard(client, tokens):
    h, uid = _new_student(client, "temp.erase@x.edu")
    assert client.delete(f"/api/privacy/admin/users/{uid}", headers=tokens["faculty"]).status_code == 403
    assert client.delete(f"/api/privacy/admin/users/{uid}", headers=tokens["admin"]).json()["deleted"] == "temp.erase@x.edu"
    me = client.get("/api/auth/me", headers=tokens["admin"]).json()
    assert client.delete(f"/api/privacy/admin/users/{me['id']}", headers=tokens["admin"]).status_code == 400  # last admin


def test_employer_deletion_closes_jobs(client):
    r = client.post("/api/auth/register", json={"full_name": "Temp Employer", "email": "temp.emp@x.edu", "password": "password123",
                                                "role": "employer", "company": "TempCo", "join_code": "COMET-UTD", "accept_terms": True}).json()
    h = {"Authorization": f"Bearer {r['token']}"}
    j = client.post("/api/match/employer/jobs", headers=h, json={"title": "Analyst", "description": "SQL"}).json()
    client.post("/api/privacy/delete-account", headers=h, json={"password": "password123", "confirm": "DELETE"})
    with SessionLocal() as db:
        job = db.get(Job, j["id"])
        assert job.employer_id is None and job.is_open is False
