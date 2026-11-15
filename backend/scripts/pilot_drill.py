"""Pilot readiness drill: demo removal, backup + restore, and verified deletion — against a real PostgreSQL.

Usage (from backend/):
  PILOT_DB=postgresql+psycopg://...pilot  RESTORE_DB=postgresql+psycopg://...restore  python scripts/pilot_drill.py

It needs pg_dump and pg_restore on PATH (or PG_BIN). RESTORE_DB is wiped. Never point PILOT_DB at a database with real data:
the drill seeds demo data, removes it, creates a test person and deletes them.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PILOT_DB, RESTORE_DB = os.environ["PILOT_DB"], os.environ["RESTORE_DB"]
PG_BIN = os.environ.get("PG_BIN", "")
os.environ.update(DATABASE_URL=PILOT_DB, SEED_DEMO="true", JOB_SYNC_ENABLED="false", TASKS_INLINE="true", ANTHROPIC_API_KEY="",
                  JWT_SECRET=os.environ.get("JWT_SECRET", "drill-secret-drill-secret-drill-secret-42"),
                  BOOTSTRAP_ADMIN_EMAIL="pilot-admin@utdallas.edu", BOOTSTRAP_ADMIN_PASSWORD="Drill-Admin-Pass-2026")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
log = []


def step(msg, ok=True):
    line = f"[{'PASS' if ok else 'FAIL'}] {msg}"
    print(line)
    log.append(line)
    if not ok:
        sys.exit(1)


def libpq(url):  # SQLAlchemy URL -> libpq URL for pg_dump/pg_restore
    return url.replace("postgresql+psycopg://", "postgresql://")


def run_cli(args, db):
    r = subprocess.run([sys.executable, "-m", "app.manage", *args], cwd=Path(__file__).resolve().parents[1],
                       env={**os.environ, "DATABASE_URL": db, "SEED_DEMO": "false"}, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

with TestClient(app) as c:
    # 1 — demo removal
    code, out = run_cli(["remove-demo-data", "--yes"], PILOT_DB)
    step(f"remove-demo-data: {out.strip().splitlines()[-1]}", code == 0)
    code, out = run_cli(["remove-demo-data"], PILOT_DB)
    step("no demo accounts, seed postings or demo syllabi remain", "Nothing to remove" in out)
    ready = c.get("/api/health/ready").json()
    step(f"readiness reports demo_accounts={ready.get('demo_accounts')}", ready.get("demo_accounts") == 0)
    step("demo sign-in no longer works", c.post("/api/auth/login", json={"email": "faculty@cometiq.app", "password": "CometIQ2026!"}).status_code == 401)

    # 2 — pilot data: a faculty member, a syllabus, a review
    adm = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "pilot-admin@utdallas.edu", "password": "Drill-Admin-Pass-2026"}).json()["token"]}
    code_ = c.get("/api/admin/org", headers=adm).json().get("join_code")
    r = c.post("/api/auth/register", json={"email": "drill.faculty@utdallas.edu", "password": "Drill-Faculty-2026", "full_name": "Drill Faculty Person",
                                           "role": "faculty", "join_code": code_, "accept_terms": True})
    step("faculty account created with the institution join code", r.status_code in (200, 201))
    fh = {"Authorization": "Bearer " + r.json()["token"]}
    uid = c.get("/api/auth/me", headers=fh).json()["id"]
    c.post("/api/jobs", headers=adm, json={"title": "Data Analyst", "company": "Drill Co", "location": "Dallas, TX", "role_family": "Data Analyst",
                                           "description": "SQL, Python, Tableau, statistics, Excel. Preferred: dbt."})
    up = c.post("/api/gap/syllabi", headers=fh, data={"title": "Drill Analytics", "code": "BUAN 6356", "target": "All roles"},
                files={"file": ("s.txt", b"Week 1: SQL joins lab. Week 2: Python pandas. Week 3: Tableau dashboards. Graded SQL project.", "text/plain")}).json()
    a = c.get(f"/api/gap/analyses/{up['analysis_id']}", headers=fh).json()
    sk = a["skills"][0]
    rv = c.put(f"/api/gap/analyses/{a['id']}/reviews/{sk['skill_id']}", headers=fh,
               json={"faculty_status": "not_relevant", "rationale": "Drill rationale written by the drill faculty person."})
    step("faculty review saved", rv.status_code == 200)
    dc = c.put(f"/api/gap/analyses/{a['id']}/decisions/{sk['skill_id']}", headers=fh,
               json={"decision": "out_of_scope", "rationale": "Drill decision recorded by the drill faculty person."})
    step("faculty decision recorded (stores the reviewer's name)", dc.status_code == 200 and dc.json()["reviewer"] == "Drill Faculty Person")

    # 3 — backup and restore
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "pilot.dump"
        subprocess.run([PG_BIN + "pg_dump", "-Fc", "--no-owner", "-f", str(dump), libpq(PILOT_DB)], check=True)
        step(f"pg_dump backup written ({dump.stat().st_size // 1024} KB)")
        subprocess.run([PG_BIN + "pg_restore", "--clean", "--if-exists", "--no-owner", "-d", libpq(RESTORE_DB), str(dump)],
                       check=True, capture_output=True)
        step("pg_restore into a separate database")
    c1, src = run_cli(["restore-check", "--json"], PILOT_DB)
    c2, dst = run_cli(["restore-check", "--json"], RESTORE_DB)
    s, d = json.loads(src[src.index("{"):]), json.loads(dst[dst.index("{"):])
    step(f"restored revision {d['revision']} matches source", s["revision"] == d["revision"] and c2 == 0)
    diff = {k: (v, d["tables"].get(k)) for k, v in s["tables"].items() if d["tables"].get(k) != v}
    step(f"row counts match in all {len(s['tables'])} tables" + (f" — differences: {diff}" if diff else ""), not diff)

    # 4 — deletion (account self-deletion) and verification
    code, out = run_cli(["verify-erasure", "--user-id", uid, "--email", "drill.faculty@utdallas.edu", "--name", "Drill Faculty Person"], PILOT_DB)
    step("before deletion the scanner finds the person (scanner works)", code == 1)
    step("faculty deletes own account", c.post("/api/privacy/delete-account", headers=fh,
                                                  json={"password": "Drill-Faculty-2026", "confirm": "DELETE"}).status_code == 200)
    code, out = run_cli(["verify-erasure", "--user-id", uid, "--email", "drill.faculty@utdallas.edu", "--name", "Drill Faculty Person"], PILOT_DB)
    step(f"live database: {out.strip()}", code == 0)
    code, out = run_cli(["verify-erasure", "--user-id", uid, "--email", "drill.faculty@utdallas.edu", "--name", "Drill Faculty Person"], RESTORE_DB)
    step(f"backup taken before deletion still contains the person until it expires ({out.strip()}) — expected; see retention", code == 1)

print("\nDrill complete:", sum(1 for x in log if x.startswith("[PASS]")), "checks passed")
