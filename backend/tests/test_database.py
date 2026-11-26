"""Database layer: full-text search, retention rules, check constraints."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError


def test_search_scoping(client, tokens):
    r = client.get("/api/search?q=sql", headers=tokens["faculty"]).json()
    assert r["results"]["courses"] and "students" not in r["results"]
    assert client.get("/api/search?q=s", headers=tokens["faculty"]).status_code == 400
    assert client.get("/api/search?q=sql&type=nope", headers=tokens["faculty"]).status_code == 400
    emp = client.get("/api/search?q=jordan&type=students", headers=tokens["employer"]).json()["results"]["students"]
    assert any(s["title"].startswith("Jordan") for s in emp)
    stu = client.get("/api/search?q=jordan&type=students", headers=tokens["student"]).json()["results"]
    assert "students" not in stu
    multi = client.get("/api/search?q=data analy&type=jobs", headers=tokens["student"]).json()["results"]["jobs"]
    assert multi


def test_retention_rules_keep_evidence(client, tokens):
    from app.db import SessionLocal
    from app.models import Job, JobSample, Notification, Organization, PasswordReset, Task, User
    from app.services import retention

    old = datetime.now(timezone.utc) - timedelta(days=800)
    with SessionLocal() as db:
        org = db.query(Organization).first()
        u = db.query(User).filter(User.email == "student@cometiq.app").one()
        db.add(Task(org_id=org.id, kind="email.send", status="done", payload={"to": "x@y.z"}, created_at=old))
        db.add(Task(org_id=org.id, kind="email.send", status="queued", payload={}, created_at=old))   # unfinished: kept
        db.add(Notification(user_id=u.id, kind="x", title="old", read_at=old, created_at=old))
        db.add(PasswordReset(user_id=u.id, token_hash="h" * 64, expires_at=old, created_at=old))
        gone = Job(title="Old synced", source="github", is_open=False, posted_at=old, external_id="ret-1")
        kept = Job(title="Old but sampled", source="github", is_open=False, posted_at=old, external_id="ret-2")
        db.add_all([gone, kept])
        db.flush()
        db.add(JobSample(org_id=org.id, name="Retention sample", method="kept as evidence for the retention test",
                         job_ids=[kept.id], kind="documented"))
        db.commit()
        gone_id, kept_id = gone.id, kept.id
        dry = retention.run(db, dry_run=True)
        assert dry["finished_tasks"] >= 1 and dry["closed_synced_postings"] >= 1
        assert db.get(Job, gone_id) is not None   # dry run changes nothing
        real = retention.run(db)
        assert real["finished_tasks"] >= 1 and real["read_notifications"] >= 1 and real["used_or_expired_password_resets"] >= 1
        assert db.get(Job, gone_id) is None and db.get(Job, kept_id) is not None
        assert db.query(Task).filter(Task.status == "queued", Task.created_at <= old + timedelta(seconds=1)).count() >= 1


@pytest.mark.parametrize("field,value", [("status", "bogus")])
def test_check_constraints_reject_invalid_values(client, field, value):
    from app.db import SessionLocal
    from app.models import Evidence, Organization, User

    with SessionLocal() as db:
        org = db.query(Organization).first()
        u = db.query(User).filter(User.email == "student@cometiq.app").one()
        db.add(Evidence(org_id=org.id, student_id=u.id, kind="course", title="x", **{field: value}))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Evidence(org_id=org.id, student_id=u.id, kind="course", title="x", bonus_points=99))
        with pytest.raises(IntegrityError):
            db.commit()


def test_cache_hits_and_invalidates_on_write(client, tokens):
    from app.services import cache

    fac = tokens["faculty"]
    def baai():
        sc = client.get("/api/curriculum/scorecard", headers=fac).json()
        return next(p for p in sc["programs"] if p["name"] == "Master of Science in Business Analytics and Artificial Intelligence")
    before = baai()
    hits = cache.stats["hits"]
    assert baai() == before and cache.stats["hits"] == hits + 1          # second read is served from the cache
    gap = before["undecided_gaps"][0]
    a = client.get(f"/api/gap/analyses/{gap['analysis_id']}", headers=fac).json()
    sid = next(s["skill_id"] for s in a["skills"] if s["name"] == gap["skill"])
    client.put(f"/api/gap/analyses/{a['id']}/reviews/{sid}", headers=fac, json={"faculty_status": "not_covered"})
    client.put(f"/api/gap/analyses/{a['id']}/decisions/{sid}", headers=fac, json={"decision": "defer", "rationale": "Revisit after the program review.", "revisit_term": "Fall 2027"})
    after = baai()                                                         # the write invalidated the cached scorecard
    assert after["undecided_count"] == before["undecided_count"] - 1
