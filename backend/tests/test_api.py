"""End-to-end API tests for CometIQ (built-in engine, seeded demo data)."""
import io

SAMPLE = """MIS 9999 Test Analytics
Week 1: Excel basics and pivot tables
Week 2: SQL joins and aggregation
Week 3: SQL window functions
Week 4: Tableau dashboards
Learning objectives
1. Write SQL queries to answer business questions.
2. Build Tableau dashboards for stakeholders.
"""


# ── Foundation ────────────────────────────────────────────────────────────────
def test_health_and_spa(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/does-not-exist").status_code == 404


def test_login_rejects_bad_password(client):
    assert client.post("/api/auth/login", json={"email": "admin@cometiq.app", "password": "nope"}).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/programs").status_code == 401


def test_rbac(client, tokens):
    assert client.get("/api/admin/users", headers=tokens["student"]).status_code == 403
    assert client.get("/api/gap/syllabi", headers=tokens["student"]).status_code == 403
    assert client.get("/api/path/overview", headers=tokens["faculty"]).status_code == 403
    assert client.get("/api/match/employer/jobs", headers=tokens["student"]).status_code == 403
    assert client.get("/api/admin/users", headers=tokens["admin"]).status_code == 200


def test_register_join_and_new_org(client):
    r = client.post("/api/auth/register", json={"full_name": "New Stu", "email": "new.stu@example.edu", "password": "password123",
                                                "role": "student", "join_code": "COMET-UTD"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "student"
    r = client.post("/api/auth/register", json={"full_name": "Dean X", "email": "dean@other.edu", "password": "password123",
                                                "role": "faculty", "org_name": "Other University"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "admin"  # creator administers the new org
    other = {"Authorization": f"Bearer {r.json()['token']}"}
    # tenant isolation: the new org has no catalog and cannot see UTD programs
    assert client.get("/api/programs", headers=other).json() == []
    assert client.post("/api/auth/register", json={"full_name": "Dup", "email": "new.stu@example.edu", "password": "password123",
                                                   "role": "student", "join_code": "COMET-UTD"}).status_code == 409


def test_catalog(client, tokens):
    progs = client.get("/api/programs", headers=tokens["student"]).json()
    assert len(progs) == 39
    c = client.get("/api/courses?q=BUAN 6341", headers=tokens["student"]).json()[0]
    d = client.get(f"/api/courses/{c['id']}", headers=tokens["student"]).json()
    assert {p["code"] for p in d["prerequisites"]} >= {"BUAN 6356", "OPRE 6359"}
    assert any(s["name"] == "Machine Learning" for s in d["skills"])


# ── CometGap ──────────────────────────────────────────────────────────────────
def test_gap_upload_analyze_export(client, tokens):
    h = tokens["faculty"]
    r = client.post("/api/gap/syllabi", headers=h, data={"title": "Test Analytics", "code": "MIS 9999", "target": "Data Analyst"},
                    files={"file": ("syllabus.txt", io.BytesIO(SAMPLE.encode()), "text/plain")})
    assert r.status_code == 201, r.text
    a = client.get(f"/api/gap/analyses/{r.json()['analysis_id']}", headers=h).json()
    assert a["target"] == "Data Analyst" and 0 <= a["score"] <= 100
    status = {s["name"]: s["status"] for s in a["skills"]}
    assert status["SQL"] == "covered" and status["Python"] == "missing"
    assert a["recommendations"] and a["counts"]["missing"] > 0
    pdf = client.get(f"/api/gap/analyses/{a['id']}/export.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/gap/analyses/{a['id']}/export.xlsx", headers=h).content[:2] == b"PK"
    # other faculty-role users can't read it
    assert client.get(f"/api/gap/analyses/{a['id']}", headers=tokens["student"]).status_code == 403


def test_gap_rejects_bad_upload(client, tokens):
    r = client.post("/api/gap/syllabi", headers=tokens["faculty"], data={"title": "x"},
                    files={"file": ("evil.exe", io.BytesIO(b"MZ..."), "application/octet-stream")})
    assert r.status_code == 400


def test_market_and_heatmap(client, tokens):
    h = tokens["faculty"]
    m = client.get("/api/gap/market?target=Data Analyst", headers=h).json()
    assert m["job_count"] > 0 and m["skills"][0]["demand"] >= m["skills"][-1]["demand"]
    pid = next(p["id"] for p in client.get("/api/programs", headers=h).json() if "Artificial Intelligence" in p["name"])
    hm = client.get(f"/api/gap/programs/{pid}?target=Data Analyst", headers=h).json()
    assert hm["courses"] and len(hm["courses"][0]["cells"]) == len(hm["skills"])


# ── CometForge ────────────────────────────────────────────────────────────────
def test_forge_generate_edit_approve(client, tokens):
    h = tokens["faculty"]
    syl = client.get("/api/gap/syllabi", headers=h).json()
    aid = next(s["latest"]["id"] for s in syl if s["code"] == "BUAN 6356")
    d = client.post("/api/forge/drafts", headers=h, json={"analysis_id": aid, "weeks": 15, "framework": "AACSB"}).json()
    c = d["content"]
    assert len(c["modules"]) == 15 and sum(a["weight"] for a in c["assessments"]) == 100
    assert any(m["is_new"] for m in c["modules"]) and c["accreditation"]
    assert d["scores"]["after"] > d["scores"]["before"]
    # invalid weights are rejected
    bad = {**c, "assessments": [{**c["assessments"][0], "weight": 5}] + c["assessments"][1:]}
    assert client.put(f"/api/forge/drafts/{d['id']}", headers=h, json={"content": bad}).status_code == 422
    c["modules"][0]["title"] = "Edited week"
    assert client.put(f"/api/forge/drafts/{d['id']}", headers=h, json={"content": c}).json()["content"]["modules"][0]["title"] == "Edited week"
    ap = client.post(f"/api/forge/drafts/{d['id']}/approve", headers=h).json()
    assert ap["status"] == "approved" and ap["graph_skills_added"] > 0
    assert client.put(f"/api/forge/drafts/{d['id']}", headers=h, json={"content": c}).status_code == 409
    assert client.get(f"/api/forge/drafts/{d['id']}/export.docx", headers=h).content[:2] == b"PK"


# ── CometPath ─────────────────────────────────────────────────────────────────
def test_path_plan_respects_prereqs_and_credits(client, tokens):
    h = tokens["student"]
    client.put("/api/path/profile", headers=h, json={**{k: v for k, v in client.get("/api/path/profile", headers=h).json().items()
                                                        if k != "career_goals"}, "career_goal": "Data Scientist"})
    plan = client.post("/api/path/plan", headers=h).json()
    assert plan["total_sch"] >= plan["required_sch"]
    assert all(t["credits"] <= 9 for t in plan["terms"])
    order = {c["code"]: i for i, t in enumerate(plan["terms"]) for c in t["courses"]}
    # BUAN 6337 requires (OPRE 6301 or BUAN 6359 or OPRE 6359): must come after BUAN 6359 when both are planned
    if "BUAN 6337" in order and "BUAN 6359" in order:
        assert order["BUAN 6359"] < order["BUAN 6337"]
    assert plan["readiness"]["with_plan"] >= plan["readiness"]["now"]
    saved = client.post("/api/path/plan?save=true", headers=h).json()
    ov = client.get("/api/path/overview", headers=h).json()
    assert ov["progress"]["sch"]["planned"] == saved["planned_sch"]


def test_path_prereq_warning(client, tokens):
    h = tokens["student"]
    cid = client.get("/api/courses?q=BUAN 6342", headers=h).json()[0]["id"]  # needs BUAN 6341
    r = client.post("/api/path/courses", headers=h, json={"course_id": cid, "status": "enrolled"}).json()
    assert r["warning"] and "BUAN 6341" in r["warning"]
    client.delete(f"/api/path/courses/{cid}", headers=h)


# ── CometMatch ────────────────────────────────────────────────────────────────
def test_match_flow(client, tokens):
    s, e = tokens["student"], tokens["employer"]
    r = client.post("/api/match/me/resume", headers=s, files={"file": ("cv.txt", io.BytesIO(b"Python, SQL, Tableau, statistics, communication"), "text/plain")})
    assert r.json()["skills_found"] >= 4
    jobs = client.get("/api/match/jobs?posted_only=true", headers=s).json()["items"]
    job = jobs[0]
    assert job["can_apply"] and 0 <= job["score"] <= 100
    detail = client.get(f"/api/match/jobs/{job['id']}", headers=s).json()
    assert len(detail["matched"]) + len(detail["partial"]) + len(detail["missing"]) == len(detail["job"]["skills"])
    assert client.post(f"/api/match/jobs/{job['id']}/apply", headers=s, json={}).status_code == 201
    assert client.post(f"/api/match/jobs/{job['id']}/apply", headers=s, json={}).status_code == 409
    cands = client.get(f"/api/match/employer/jobs/{job['id']}/candidates", headers=e).json()["candidates"]
    scores = [c["score"] for c in cands if c["application"] is None]
    assert scores == sorted(scores, reverse=True)
    me = next(c for c in cands if c["application"])
    assert client.post(f"/api/match/employer/jobs/{job['id']}/candidates/{me['student']['id']}", headers=e, json={"status": "interview"}).json()["status"] == "interview"
    assert client.get("/api/match/employer/pipeline", headers=e).json()["interview"]
    # market (non-partner) jobs can't be applied to inside CometIQ
    market = next(j for j in client.get("/api/match/jobs", headers=s).json()["items"] if not j["can_apply"])
    assert client.post(f"/api/match/jobs/{market['id']}/apply", headers=s, json={}).status_code == 400


def test_employer_post_with_alternatives(client, tokens):
    e = tokens["employer"]
    j = client.post("/api/match/employer/jobs", headers=e, json={"title": "BI Analyst", "location": "Dallas, TX",
                    "description": "Required qualifications:\n- Tableau or Power BI\n- SQL\n\nPreferred qualifications:\n- Python"}).json()
    imp = {s["name"]: s["importance"] for s in j["skills"]}
    assert imp["Tableau"] == "required" and imp["Power BI"] == "preferred" and imp["Python"] == "preferred"


def test_impact(client, tokens):
    d = client.get("/api/dashboard/impact", headers=tokens["admin"]).json()
    assert d["curricula"]["syllabi_analyzed"] >= 1 and d["outcomes"]["applications"] >= 1
