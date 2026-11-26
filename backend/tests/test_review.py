"""Faculty review: evidence per skill, documented job samples, corrections, pilot tracking and operations commands."""
import csv
import io

from tests.test_api import SAMPLE


def _upload(client, h, **data):
    r = client.post("/api/gap/syllabi", headers=h, data={"title": "Review Analytics", "code": "MIS 9998", "target": "Data Analyst", **data},
                    files={"file": ("syllabus.txt", io.BytesIO(SAMPLE.encode()), "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def test_documented_sample_and_evidence_per_skill(client, tokens):
    h = tokens["faculty"]
    bad = client.post("/api/gap/samples", headers=h, json={"name": "Too short", "method": "short"})
    assert bad.status_code == 422
    none = client.post("/api/gap/samples", headers=h, json={"name": "Empty", "method": "Postings titled zzz nothing matches this.", "query": "zzzqqq"})
    assert none.status_code == 400
    smp = client.post("/api/gap/samples", headers=h, json={
        "name": "DFW analyst postings", "role_family": "Data Analyst",
        "method": "All open Data Analyst postings in CometIQ on the sample date; no manual exclusions."}).json()
    assert smp["total"] >= 5 and smp["sources"] and smp["date_from"] and smp["date_to"]
    up = _upload(client, h, sample_id=smp["id"])
    a = client.get(f"/api/gap/analyses/{up['analysis_id']}", headers=h).json()
    prov = a["provenance"]
    assert prov["sample"]["name"] == "DFW analyst postings" and prov["total"] == smp["total"] and prov["date_from"]
    assert a["score_basis"] == "mentions"
    sql = next(s for s in a["skills"] if s["name"] == "SQL")
    assert sql["excerpts"] and any("SQL" in e for e in sql["excerpts"])
    assert sql["job_count"] == sql["required_count"] + sql["preferred_count"] and sql["sources"]
    # the frozen sample can be downloaded with its method, and can't be deleted while used
    csv_txt = client.get(f"/api/gap/samples/{smp['id']}/postings.csv", headers=h).text
    assert "# Method: All open Data Analyst" in csv_txt
    assert client.delete(f"/api/gap/samples/{smp['id']}", headers=h).status_code == 409
    assert client.get("/api/gap/samples", headers=tokens["student"]).status_code == 403


def test_faculty_review_corrections_and_pilot_tracking(client, tokens):
    h = tokens["faculty"]
    up = _upload(client, h)
    aid = up["analysis_id"]
    a = client.get(f"/api/gap/analyses/{aid}", headers=h).json()
    sql = next(s for s in a["skills"] if s["name"] == "SQL")        # covered by mentions
    py = next(s for s in a["skills"] if s["name"] == "Python")      # missing
    url = f"/api/gap/analyses/{aid}/reviews"
    # confirming needs no rationale
    r = client.put(f"{url}/{py['skill_id']}", headers=h, json={"faculty_status": "not_covered", "action": "planned", "action_note": "Add a Python lab"})
    assert r.status_code == 200 and r.json()["review"]["decision"] == "confirmed"
    # correcting requires a rationale
    assert client.put(f"{url}/{sql['skill_id']}", headers=h, json={"faculty_status": "mentioned_only"}).status_code == 400
    r = client.put(f"{url}/{sql['skill_id']}", headers=h, json={
        "faculty_status": "mentioned_only", "rationale": "SQL appears in the reading list only; no graded SQL assignment."})
    assert r.status_code == 200 and r.json()["review"]["decision"] == "corrected"
    summ = r.json()["review_summary"]
    assert summ["confirmed"] == 1 and summ["corrected"] == 1 and summ["planned"] == 1
    assert summ["reviewed_score"] is not None
    assert client.put(f"{url}/{py['skill_id']}", headers=h, json={"faculty_status": "bogus"}).status_code == 400
    assert client.put(f"{url}/999999", headers=h, json={"faculty_status": "practiced"}).status_code == 404
    assert client.put(f"{url}/{py['skill_id']}", headers=tokens["student"], json={"faculty_status": "practiced"}).status_code == 403
    # the detail view returns the reviews and the export carries the rationale
    d = client.get(f"/api/gap/analyses/{aid}", headers=h).json()
    assert d["reviews"][str(sql["skill_id"])]["rationale"].startswith("SQL appears")
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/gap/analyses/{aid}/findings.csv", headers=h).text.lstrip("﻿"))))
    row = next(x for x in rows if x["skill"] == "SQL")
    assert row["decision"] == "corrected" and row["syllabus_excerpt"] and row["postings_in_sample"]
    # re-analysis carries reviews forward
    a2 = client.post(f"/api/gap/syllabi/{up['syllabus_id']}/analyze", headers=h, json={"target": "Data Analyst"}).json()
    d2 = client.get(f"/api/gap/analyses/{a2['id']}", headers=h).json()
    assert str(sql["skill_id"]) in d2["reviews"] and d2["reviews"][str(sql["skill_id"])]["carried_from"] == aid
    # pilot: only approved syllabi count; approval needs an approver
    sid = up["syllabus_id"]
    assert client.post(f"/api/gap/syllabi/{sid}/approval", headers=h, json={"approved": True}).status_code == 400
    assert client.post(f"/api/gap/syllabi/{sid}/approval", headers=h, json={"approved": True, "approved_by": "Dr. Instructor of record"}).json()["pilot_approved"]
    p = client.get("/api/gap/pilot/summary", headers=h).json()
    mine = next(x for x in p["syllabi"] if x["syllabus_id"] == sid)
    assert mine["corrected"] == 1 and mine["approved_by"] == "Dr. Instructor of record"
    assert any(c["skill"] == "SQL" for c in p["corrections"])
    assert "MIS 9998" in client.get("/api/gap/pilot/findings.csv", headers=h).text
    # clearing a review
    assert client.delete(f"{url}/{py['skill_id']}", headers=h).status_code == 200


def test_catalog_year_confirmation(client, tokens):
    pid = client.get("/api/programs", headers=tokens["admin"]).json()[0]["id"]
    assert client.get(f"/api/programs/{pid}", headers=tokens["admin"]).json()["catalog_year"]
    body = {"catalog_year": "2025-26", "confirmed_by": "Program director", "note": "Confirmed by email"}
    assert client.put(f"/api/programs/{pid}/catalog-confirmation", headers=tokens["faculty"], json=body).status_code == 403
    assert client.put(f"/api/programs/{pid}/catalog-confirmation", headers=tokens["admin"], json={**body, "catalog_year": "25-26"}).status_code == 422
    r = client.put(f"/api/programs/{pid}/catalog-confirmation", headers=tokens["admin"], json=body)
    assert r.status_code == 200
    d = client.get(f"/api/programs/{pid}", headers=tokens["admin"]).json()
    assert d["catalog_confirmed_by"] == "Program director" and d["catalog_confirmed_at"]


def test_pilot_roles_block_other_roles(client, tokens, monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "PILOT_ROLES", "admin,faculty")
    assert client.get("/api/auth/public-config").json()["pilot_roles"] == ["admin", "faculty"]
    assert client.get("/api/auth/me", headers=tokens["student"]).status_code == 403
    assert client.get("/api/auth/me", headers=tokens["faculty"]).status_code == 200
    r = client.post("/api/auth/login", json={"email": "employer@cometiq.app", "password": "CometIQ2026!"})
    assert r.status_code == 403
    r = client.post("/api/auth/register", json={"email": "s-pilot@utd.edu", "password": "LongPassword1!", "full_name": "S P",
                                                 "role": "student", "join_code": "COMET-UTD", "accept_terms": True})
    assert r.status_code in (400, 403)
    assert client.get("/api/health/ready").json()["pilot_roles"] == ["admin", "faculty"]


def test_manage_commands(client, tokens, capsys):
    from app import manage

    assert manage.restore_check(True) == 0
    out = capsys.readouterr().out
    assert '"revision"' in out and '"users"' in out
    assert manage.remove_demo_data(False) == 0 and "Dry run" in capsys.readouterr().out
    # register a person, erase them, and prove nothing is left
    r = client.post("/api/auth/register", json={"email": "erase.me@utd.edu", "password": "LongPassword1!", "full_name": "Erase Me Testperson",
                                                 "role": "student", "join_code": "COMET-UTD", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    uid = client.get("/api/auth/me", headers=h).json()["id"]
    assert manage.verify_erasure(uid, "erase.me@utd.edu", "Erase Me Testperson") == 1
    capsys.readouterr()
    assert client.post("/api/privacy/delete-account", headers=h, json={"password": "LongPassword1!", "confirm": "DELETE"}).status_code == 200
    assert manage.verify_erasure(uid, "erase.me@utd.edu", "Erase Me Testperson") == 0, capsys.readouterr().out
