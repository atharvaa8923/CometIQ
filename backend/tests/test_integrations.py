"""Job sources, nightly sync locking and the Claude code path (with fake clients — no network)."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Job, SyncRun
from app.services import ai, sources
from app.services import skills as sk
from app.services import sync as syncsvc

FIX = Path(__file__).parent / "fixtures"


def test_usajobs_parsing(monkeypatch):
    sample = json.loads((FIX / "usajobs_sample.json").read_text())
    seen = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return R()

    monkeypatch.setattr(get_settings(), "USAJOBS_API_KEY", "k")
    monkeypatch.setattr(get_settings(), "USAJOBS_EMAIL", "ops@example.edu")
    monkeypatch.setattr(sources.httpx, "get", fake_get)
    rows = sources.fetch_usajobs("data analyst", "Dallas")
    assert seen["headers"]["Authorization-Key"] == "k" and seen["headers"]["User-Agent"] == "ops@example.edu"
    assert seen["params"]["Keyword"] == "data analyst"
    assert [r["title"] for r in rows] == ["Data Analyst", "IT Specialist (INFOSEC)"]
    assert rows[1]["company"] == "Department of Homeland Security" and rows[0]["external_id"] == "TX-26-0001"
    assert "Required qualifications" in rows[0]["description"]


def test_sync_partial_failure_and_dedupe(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "USAJOBS_API_KEY", "k")
    monkeypatch.setattr(get_settings(), "USAJOBS_EMAIL", "ops@example.edu")
    rows = [{"title": "Data Analyst", "company": "Agency", "location": "Dallas, Texas", "external_id": "X-1", "source": "usajobs",
             "description": "Required qualifications:\n- SQL and Tableau\n- Statistics"}]

    def fake_fetch(name):
        if name == "github":
            raise RuntimeError("network down")
        return rows

    monkeypatch.setattr(syncsvc, "_fetch", fake_fetch)
    with SessionLocal() as db:
        run = syncsvc.run_sync(db, syncsvc.start_run(db, "manual"))
        assert run.status == "partial"
        assert run.results["usajobs"] == {"fetched": 1, "added": 1} and "error" in run.results["github"]
        run2 = syncsvc.run_sync(db, syncsvc.start_run(db, "manual"))
        assert run2.results["usajobs"]["added"] == 0  # deduplicated by source + external_id
        job = db.scalar(select(Job).where(Job.external_id == "X-1"))
        assert {s.skill.name for s in job.skills} >= {"SQL", "Tableau", "Statistics"}


def test_nightly_lock_is_unique(client):
    with SessionLocal() as db:
        key = "nightly-2099-01-01"
        assert syncsvc.start_run(db, "nightly", key) is not None
        assert syncsvc.start_run(db, "nightly", key) is None  # a second worker cannot start the same nightly run
        assert db.scalar(select(SyncRun).where(SyncRun.run_key == key)).trigger == "nightly"
    assert syncsvc.nightly_due(datetime(2026, 1, 1, 3, tzinfo=timezone.utc)) is None
    assert syncsvc.nightly_due(datetime(2026, 1, 1, 23, tzinfo=timezone.utc)) == "nightly-2026-01-01"


def test_admin_integrations(client, tokens):
    r = client.get("/api/admin/integrations", headers=tokens["admin"]).json()
    assert set(r["job_sources"]) == {"github", "adzuna", "usajobs", "handshake"} and r["job_sources"]["github"]["enabled"]
    inst = r["institution"]
    assert set(inst) == {"sso", "canvas", "credentials", "open_badges", "handshake"} and inst["open_badges"]["enabled"]
    assert not inst["sso"]["enabled"] and not inst["canvas"]["enabled"] and not inst["credentials"]["enabled"]
    assert client.get("/api/admin/integrations", headers=tokens["faculty"]).status_code == 403
    assert client.post("/api/admin/ai/test", headers=tokens["admin"]).json()["ok"] is False  # no key in tests


# ── Claude path with a fake Anthropic client ──────────────────────────────────
class _Msg:
    def __init__(self, parsed, stop="end_turn"):
        self.parsed_output, self.stop_reason = parsed, stop


def _fake_client(parsed_factory, stop="end_turn", calls=None):
    class Messages:
        @contextmanager
        def stream(self, **kw):
            if calls is not None:
                calls.append(kw)

            class S:
                def get_final_message(self_inner):
                    return _Msg(parsed_factory(kw["output_format"]), stop)
            yield S()

    class Beta:
        messages = Messages()

    class Client:
        beta = Beta()
    return Client()


def test_claude_structured_success_and_refusal(monkeypatch):
    class Out(BaseModel):
        skills: list[str]

    calls = []
    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(ai, "_client", _fake_client(lambda schema: schema(skills=["SQL"]), calls=calls))
    assert ai.structured("sys", "prompt", Out).skills == ["SQL"]
    kw = calls[0]
    assert kw["model"] == get_settings().AI_MODEL and kw["output_format"] is Out and kw["fallbacks"] == "default"
    monkeypatch.setattr(ai, "_client", _fake_client(lambda schema: schema(skills=["x"]), stop="refusal"))
    assert ai.structured("sys", "prompt", Out) is None  # refusal → built-in fallback
    monkeypatch.setattr(ai, "_client", None)


def test_claude_extraction_merges_and_filters(monkeypatch):
    def parsed(schema):
        return schema(skills=[{"skill": "Machine Learning", "evidence": "built predictive models", "importance": "required"},
                              {"skill": "Underwater Basket Weaving", "evidence": "?", "importance": "required"}])

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(ai, "_client", _fake_client(parsed))
    found, engine = sk.extract("I built predictive models for churn using SQL queries and dashboards.", kind="resume")
    assert engine == "claude"
    assert "Machine Learning" in found and "SQL" in found          # Claude adds what keywords miss; built-in still counts
    assert "Underwater Basket Weaving" not in found                 # anything outside the taxonomy is dropped
    monkeypatch.setattr(ai, "_client", None)


def test_login_rate_limit_and_headers(client):
    from app.routers import auth as authmod

    authmod._failures.clear()
    for _ in range(10):
        assert client.post("/api/auth/login", json={"email": "nobody@x.edu", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@x.edu", "password": "wrong-pass"}).status_code == 429
    authmod._failures.clear()
    r = client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    cfg = client.get("/api/auth/public-config").json()
    assert cfg["demo"] is True and cfg["pilot_roles"] is None and cfg["sso"]["enabled"] is False


def test_production_seed_has_no_demo_users(tmp_path, monkeypatch):
    """Fresh database in production mode: catalog + bootstrap admin, no public demo accounts."""
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker

    from app import seed as seedmod
    from app.db import Base
    from app.models import Course, Organization, User

    eng = create_engine(f"sqlite:///{tmp_path}/prod.db")
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    s = get_settings()
    monkeypatch.setattr(s, "SEED_DEMO", False)
    monkeypatch.setattr(s, "BOOTSTRAP_ADMIN_EMAIL", "it@utdallas.edu")
    monkeypatch.setattr(s, "BOOTSTRAP_ADMIN_PASSWORD", "a-very-long-password")
    with S() as db:
        seedmod.sync_skills(db)
        seedmod.seed_production(db)
        seedmod.ensure_bootstrap_admin(db)  # same session, as in init_db: must not duplicate the admin
        db.commit()
        seedmod.ensure_bootstrap_admin(db)  # later restarts
        db.commit()
        assert db.scalar(select(func.count()).select_from(Course)) == 331
        emails = set(db.scalars(select(User.email)))
        assert emails == {"it@utdallas.edu"}
        assert db.scalar(select(Organization.join_code)).startswith("COMET-")
