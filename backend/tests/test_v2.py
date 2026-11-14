"""Tests for evidence verification, talent search, learn-next, AI fallbacks, advisor reviews, what-if, PDFs and Nebula."""
import io
import json
from pathlib import Path

from app.config import get_settings
from app.services import nebula

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _skill_ids(client, h, *names):
    sk = {s["name"]: s["id"] for s in client.get("/api/skills", headers=h).json()}
    return [sk[n] for n in names]


def test_evidence_verification_adds_bonus(client, tokens):
    s, a = tokens["student"], tokens["admin"]
    jobs = client.get("/api/match/jobs", headers=s).json()["items"]
    job = next(j for j in jobs if any(k["name"] == "AWS" for k in j["skills"]))
    before = client.get(f"/api/match/jobs/{job['id']}", headers=s).json()
    r = client.post("/api/evidence", headers=s, data={"kind": "certification", "title": "AWS Certified Cloud Practitioner",
                    "description": "EC2, S3, IAM, cloud computing and cloud security"}, files={"file": ("c.pdf", io.BytesIO(PDF), "application/pdf")})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    eid = r.json()["id"]
    assert client.post(f"/api/evidence/{eid}/review", headers=s, json={"decision": "verified"}).status_code == 403
    assert client.get(f"/api/evidence/{eid}/file", headers=tokens["employer"]).status_code in (403, 404)
    assert client.post(f"/api/evidence/{eid}/review", headers=a, json={"decision": "rejected"}).status_code == 400  # note required
    v = client.post(f"/api/evidence/{eid}/review", headers=tokens["advisor"], json={"decision": "verified"}).json()
    assert v["status"] == "verified" and v["bonus_points"] == 10
    after = client.get(f"/api/match/jobs/{job['id']}", headers=s).json()
    assert after["bonus"] == 10 and after["score"] == min(100, after["base_score"] + 10)
    assert after["score"] > before["score"]
    assert client.delete(f"/api/evidence/{eid}", headers=s).status_code == 409  # verified is locked


def test_evidence_rejects_non_documents(client, tokens):
    r = client.post("/api/evidence", headers=tokens["student"], data={"kind": "project", "title": "My project", "description": "x"},
                    files={"file": ("x.pdf", io.BytesIO(b"<script>alert(1)</script>"), "application/pdf")})
    assert r.status_code == 400
    r = client.post("/api/evidence", headers=tokens["student"], data={"kind": "certification", "title": "Cert without proof"})
    assert r.status_code == 400


def test_verified_course_marks_completed(client, tokens):
    s = tokens["student"]
    cid = client.get("/api/courses?q=MIS 6309", headers=s).json()[0]["id"]
    e = client.post("/api/evidence", headers=s, data={"kind": "course", "title": "Business Data Warehousing", "course_id": cid,
                    "description": "Star schemas and data warehousing"}).json()
    client.post(f"/api/evidence/{e['id']}/review", headers=tokens["admin"], json={"decision": "verified"})
    courses = client.get("/api/path/overview", headers=s).json()["courses"]
    assert any(c["course_id"] == cid and c["status"] == "completed" for c in courses)


def test_talent_search_and_learn_next(client, tokens):
    e = tokens["employer"]
    ids = _skill_ids(client, e, "Python", "SQL")
    res = client.get(f"/api/match/employer/talent?skills={ids[0]},{ids[1]}", headers=e).json()
    scores = [r["score"] for r in res["results"]]
    assert res["searched"] == ["Python", "SQL"] and scores == sorted(scores, reverse=True) and scores[0] == 100
    assert client.get("/api/match/employer/talent", headers=tokens["student"]).status_code == 403
    ln = client.get("/api/match/learn-next", headers=tokens["student"]).json()
    assert ln["skills"] and all(x["points"] > 0 for x in ln["skills"])
    pts = [x["points"] for x in ln["skills"]]
    assert pts == sorted(pts, reverse=True)


def test_explain_and_resume_tips_builtin(client, tokens):
    s = tokens["student"]
    job = client.get("/api/match/jobs?posted_only=true", headers=s).json()["items"][0]
    x = client.post(f"/api/match/jobs/{job['id']}/explain", headers=s).json()
    assert x["engine"] == "builtin" and x["headline"] and x["strengths"] and x["next_steps"]
    t = client.post("/api/match/me/resume-tips", headers=s).json()
    assert t["tips"] and all(tip["priority"] in ("high", "medium", "low") for tip in t["tips"])


def test_advisor_review_flow_and_pdf(client, tokens):
    s, adv = tokens["student"], tokens["advisor"]
    client.post("/api/path/plan?save=true", headers=s)
    r = client.post("/api/path/review", headers=s, json={"note": "Please review"}).json()
    assert r["status"] == "submitted"
    assert client.get("/api/advising/students", headers=s).status_code == 403
    assert client.get("/api/advising/students", headers=tokens["faculty"]).status_code == 403
    queue = client.get("/api/advising/students?status=submitted", headers=adv).json()
    me = next(q for q in queue if q["review_id"] == r["id"])
    detail = client.get(f"/api/advising/students/{me['id']}", headers=adv).json()
    assert detail["snapshot"]["terms"]
    assert client.post(f"/api/advising/reviews/{r['id']}", headers=adv, json={"decision": "changes_requested"}).status_code == 400
    ok = client.post(f"/api/advising/reviews/{r['id']}", headers=adv, json={"decision": "approved", "note": "Good"}).json()
    assert ok["status"] == "approved" and ok["advisor"]
    assert client.get("/api/path/review", headers=s).json()["status"] == "approved"
    pdf = client.get("/api/path/plan.pdf", headers=s)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/advising/students/{me['id']}/plan.pdf", headers=adv).content[:4] == b"%PDF"


def test_what_if(client, tokens):
    s = tokens["student"]
    fin = next(p for p in client.get("/api/programs", headers=s).json() if p["name"] == "Master of Science in Finance")
    w = client.post("/api/path/what-if", headers=s, json={"program_id": fin["id"], "career_goal": "Financial Analyst"}).json()
    assert w["what_if"]["program"]["name"] == "Master of Science in Finance"
    assert "BUAN 6312" in w["what_if"]["not_counted_courses"]          # analytics core doesn't count for Finance
    assert w["what_if"]["total_sch"] >= w["what_if"]["required_sch"]
    assert "comparison" in w
    # profile is unchanged by a what-if
    assert client.get("/api/path/profile", headers=s).json()["program_id"] != fin["id"]


def test_nebula_not_configured(client, tokens):
    cid = client.get("/api/courses?q=BUAN 6341", headers=tokens["student"]).json()[0]["id"]
    r = client.get(f"/api/courses/{cid}/live", headers=tokens["student"]).json()
    assert r["configured"] is False and r["available"] is False


def test_nebula_summary_with_fixture(client, tokens, monkeypatch):
    sample = json.loads((Path(__file__).parent / "fixtures" / "nebula_trends_sample.json").read_text())
    calls = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return Resp()

    monkeypatch.setattr(get_settings(), "NEBULA_API_KEY", "test-key")
    monkeypatch.setattr(nebula.httpx, "get", fake_get)
    nebula._cache.clear()
    cid = client.get("/api/courses?q=BUAN 6341", headers=tokens["student"]).json()[0]["id"]
    r = client.get(f"/api/courses/{cid}/live", headers=tokens["student"]).json()
    client.get(f"/api/courses/{cid}/live", headers=tokens["student"])  # cached
    assert len(calls) == 1
    url, params, headers = calls[0]
    assert url.endswith("/course/sections/trends") and params == {"subject_prefix": "BUAN", "course_number": "6341"}
    assert headers["x-api-key"] == "test-key"
    assert r["available"] and r["latest_term"] == "Fall 2025" and r["terms_offered"] == ["Fall 2025", "Spring 2025"]
    assert [s["section"] for s in r["sections"]] == ["001", "501"]
    assert r["sections"][0]["meetings"][0]["location"] == "JSOM 2.106"
    g = r["grades"]
    assert g["students"] == sum(sum(x["grade_distribution"]) for x in sample["data"])
    assert 3.0 < g["gpa"] < 4.0 and g["distribution"][-1]["grade"] == "W"
    assert r["professors"][0]["name"] == "Ada Lovelace"  # higher GPA ranks first
    nebula._cache.clear()
