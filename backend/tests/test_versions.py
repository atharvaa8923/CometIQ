"""Syllabus/sample/catalog/scoring versions, semester comparison with attribution, reproducibility, faculty decisions."""
import csv
import io

V1 = """MIS 9997 Analytics Studio
Week 1: SQL joins and aggregation lab
Week 2: SQL window functions
Week 3: Excel pivot tables and Excel dashboards
Week 4: Statistics review and hypothesis testing
Graded project: SQL report for a retail client
"""
V2 = V1 + "Week 5: Python pandas lab\nWeek 6: Python visualization assignment (graded)\n"


def _sample(client, h, name, **crit):
    r = client.post("/api/gap/samples", headers=h, json={"name": name, "method": "Frozen for the versioning tests; all matching open postings.", **crit})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _skill(a, name):
    return next(s for s in a["skills"] if s["name"] == name)


def test_versions_comparison_reproducibility_and_decisions(client, tokens, monkeypatch):
    h = tokens["faculty"]
    s1 = _sample(client, h, "Analyst sample", role_family="Data Analyst")
    s2 = _sample(client, h, "All roles sample")
    up = client.post("/api/gap/syllabi", headers=h, data={"title": "Analytics Studio", "code": "MIS 9997", "semester": "Spring 2027",
                                                          "sample_id": s1}, files={"file": ("v1.txt", io.BytesIO(V1.encode()), "text/plain")}).json()
    sid = client.get("/api/gap/syllabi", headers=h).json()
    sid = next(x["id"] for x in sid if x["code"] == "MIS 9997")
    a1 = client.get(f"/api/gap/analyses/{up['analysis_id']}", headers=h).json()
    assert a1["inputs"]["recorded"] and a1["inputs"]["syllabus"]["version"] == 1 and a1["inputs"]["sample"]["kind"] == "documented"
    rep = client.get(f"/api/gap/analyses/{a1['id']}/reproduce", headers=h).json()
    assert rep["reproducible"] and rep["exact"], rep
    assert _skill(a1, "Python")["status"] == "missing" and _skill(a1, "SQL")["status"] == "covered"

    # ── decisions on reviewed gaps ──
    py, xl = _skill(a1, "Python")["skill_id"], _skill(a1, "SQL")["skill_id"]
    dec = f"/api/gap/analyses/{a1['id']}/decisions"
    assert client.put(f"{dec}/{py}", headers=h, json={"decision": "add_here", "rationale": "Employers ask for it everywhere."}).status_code == 400  # not reviewed
    client.put(f"/api/gap/analyses/{a1['id']}/reviews/{py}", headers=h, json={"faculty_status": "not_covered"})
    assert client.put(f"{dec}/{py}", headers=h, json={"decision": "add_here", "rationale": "short"}).status_code == 400
    assert client.put(f"{dec}/{py}", headers=h, json={"decision": "nope", "rationale": "Employers ask for it everywhere."}).status_code == 400
    d_py = client.put(f"{dec}/{py}", headers=h, json={"decision": "add_here", "rationale": "Every analyst posting in the sample asks for Python."}).json()
    assert d_py["reviewer"] and d_py["evidence"]["syllabus_version"] == 1 and d_py["evidence"]["sample_name"] == "Analyst sample"
    assert d_py["evidence"]["scoring_version"] and d_py["evidence"]["postings_requesting"] > 0
    client.put(f"/api/gap/analyses/{a1['id']}/reviews/{xl}", headers=h, json={"faculty_status": "practiced"})
    assert client.put(f"{dec}/{xl}", headers=h, json={"decision": "defer", "rationale": "Nothing to decide here really."}).status_code == 400
    gaps = [g for g in a1["gaps"] if g["skill_id"] != py][:2]
    g1, g2 = gaps[0]["skill_id"], gaps[1]["skill_id"]
    for g in (g1, g2):
        client.put(f"/api/gap/analyses/{a1['id']}/reviews/{g}", headers=h, json={"faculty_status": "not_covered"})
    assert client.put(f"{dec}/{g1}", headers=h, json={"decision": "covered_elsewhere", "rationale": "Taught in the database course.",
                                                     "covered_in": ["ZZZ 0000"]}).status_code == 400
    ok = client.put(f"{dec}/{g1}", headers=h, json={"decision": "covered_elsewhere", "rationale": "Taught in the database course.",
                                                   "covered_in": ["buan 6320"]}).json()
    assert ok["covered_in"] == ["BUAN 6320"]
    assert client.put(f"{dec}/{g2}", headers=h, json={"decision": "defer", "rationale": "Revisit after the program review."}).status_code == 400
    first = client.put(f"{dec}/{g2}", headers=h, json={"decision": "defer", "rationale": "Revisit after the program review.", "revisit_term": "Fall 2027"}).json()
    second = client.put(f"{dec}/{g2}", headers=h, json={"decision": "out_of_scope", "rationale": "Belongs in the capstone, not here."}).json()
    lst = client.get(f"/api/gap/syllabi/{sid}/decisions", headers=h).json()
    assert {d["id"] for d in lst["history"]} == {first["id"]} and lst["history"][0]["superseded_by"] == second["id"]
    assert len(lst["active"]) == 3

    # accepted change → CometForge draft → side-by-side
    t = client.post(f"/api/gap/syllabi/{sid}/decisions/draft", headers=h).json()
    assert client.get(f"/api/tasks/{t['task_id']}", headers=h).json()["status"] == "done"
    d_now = next(d for d in client.get(f"/api/gap/syllabi/{sid}/decisions", headers=h).json()["active"] if d["id"] == d_py["id"])
    assert d_now["status"] == "drafted" and d_now["forge_draft_id"]
    pc = client.get(f"/api/gap/syllabi/{sid}/proposed-changes", headers=h).json()
    assert pc["draft"]["id"] == d_now["forge_draft_id"] and pc["current_lines"]
    item = next(x for x in pc["skills"] if x["skill"] == "Python")
    assert item["current"] == [] and (item["proposed"]["modules"] or item["proposed"]["outcomes"] or item["proposed"]["assessments"])
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/gap/analyses/{a1['id']}/findings.csv", headers=h).text.lstrip("﻿"))))
    assert next(r for r in rows if r["skill"] == "Python")["course_decision"] == "Add to this course"
    p = client.get("/api/gap/pilot/summary?approved_only=false", headers=h).json()
    assert p["totals"]["decisions"]["add_here"] >= 1

    # ── new semester version: course revision ──
    t = client.post(f"/api/gap/syllabi/{sid}/versions", headers=h, data={"semester": "Fall 2027", "change_note": "Added a Python unit"},
                    files={"file": ("v2.txt", io.BytesIO(V2.encode()), "text/plain")}).json()
    a2_id = client.get(f"/api/tasks/{t['task_id']}", headers=h).json()["result"]["analysis_id"]
    a2 = client.get(f"/api/gap/analyses/{a2_id}", headers=h).json()
    assert a2["inputs"]["syllabus"]["version"] == 2 and a2["inputs"]["sample"]["name"] == "Analyst sample"   # same sample kept
    assert _skill(a2, "Python")["status"] == "covered"
    assert a2["reviews"] == {}   # reviews judged v1; the revised syllabus needs a fresh review
    d_now = next(d for d in client.get(f"/api/gap/syllabi/{sid}/decisions", headers=h).json()["active"] if d["id"] == d_py["id"])
    assert d_now["detected_in_version"] == 2 and d_now["status"] == "drafted"   # flagged, not auto-closed
    assert client.post(f"/api/gap/decisions/{d_py['id']}/status", headers=h, json={"status": "implemented", "note": "Python unit added"}).json()["status"] == "implemented"
    assert client.post(f"/api/gap/decisions/{ok['id']}/status", headers=h, json={"status": "implemented"}).status_code == 400
    c = client.get(f"/api/gap/compare?a={a1['id']}&b={a2_id}", headers=h).json()
    e = c["effects"]
    assert e["course_revision"] > 0 and e["demand_change"] == 0 and e["method_update"] == 0
    assert abs(sum(e.values()) - c["total"]) < 0.2
    assert any(x["skill"] == "Python" and x["reasons"] == ["course revision"] for x in c["skills"])
    assert c["syllabus"]["changed"] and any("Python" in ln for ln in c["syllabus"]["added"]) and c["sample"]["same"]

    # ── different job sample: demand change ──
    t = client.post(f"/api/gap/syllabi/{sid}/analyze", headers=h, json={"target": "Data Analyst", "sample_id": s2}).json()
    a3_id = t["id"]
    c = client.get(f"/api/gap/compare?a={a2_id}&b={a3_id}", headers=h).json()
    assert c["effects"]["course_revision"] == 0 and c["effects"]["demand_change"] != 0 and c["effects"]["method_update"] == 0
    assert abs(sum(c["effects"].values()) - c["total"]) < 0.2 and not c["sample"]["same"]

    # ── scoring update: method change; old reports stay reproducible ──
    from app.services import versions as vs

    current = vs.SCORING_VERSION
    old = vs.SCORERS[current]

    def stricter(skills, topics, demand, top_n):
        rows, sc = old(skills, topics, demand, top_n)
        return rows, round(sc * 0.9, 1)

    monkeypatch.setitem(vs.SCORERS, "2099.01", stricter)
    monkeypatch.setattr(vs, "SCORING_VERSION", "2099.01")
    a4_id = client.post(f"/api/gap/syllabi/{sid}/analyze", headers=h, json={"target": "Data Analyst", "sample_id": s2}).json()["id"]
    c = client.get(f"/api/gap/compare?a={a3_id}&b={a4_id}", headers=h).json()
    assert c["effects"]["method_update"] < 0 and c["effects"]["course_revision"] == 0 and c["effects"]["demand_change"] == 0
    r3 = client.get(f"/api/gap/analyses/{a3_id}/reproduce", headers=h).json()
    assert r3["exact"] and r3["scoring_version"] == current and r3["current_method_score"] < r3["stored_score"]

    hist = client.get(f"/api/gap/syllabi/{sid}/history", headers=h).json()
    assert [v["version"] for v in hist["versions"]] == [1, 2] and len(hist["reports"]) == 4 and len(hist["steps"]) == 3
    assert hist["versions"][1]["change_note"] == "Added a Python unit"
    txt = client.get(f"/api/gap/syllabi/{sid}/versions/{hist['versions'][0]['id']}/text", headers=h).json()
    assert "Python" not in txt["text"]


def test_live_target_snapshot_is_hidden_and_legacy_reports(client, tokens):
    h = tokens["faculty"]
    up = client.post("/api/gap/syllabi", headers=h, data={"title": "Snap", "code": "MIS 9996", "target": "Data Analyst", "text": V1}).json()
    a = client.get(f"/api/gap/analyses/{up['analysis_id']}", headers=h).json()
    assert a["sample_id"] is None and a["inputs"]["sample"]["kind"] == "auto" and a["inputs"]["recorded"]
    assert all(s["name"] != a["inputs"]["sample"]["name"] for s in client.get("/api/gap/samples", headers=h).json())
    # postings change after the analysis: the report still reproduces from its snapshot
    from app.db import SessionLocal
    from app.models import GapAnalysis, Job

    with SessionLocal() as db:
        db.query(Job).filter(Job.role_family == "Data Analyst").update({"is_open": False})
        db.commit()
    assert client.get(f"/api/gap/analyses/{a['id']}/reproduce", headers=h).json()["exact"]
    with SessionLocal() as db:
        db.query(Job).filter(Job.role_family == "Data Analyst").update({"is_open": True})
        ga = db.get(GapAnalysis, a["id"])
        ga.syllabus_version_id = None   # like a report made before versioning
        db.commit()
    r = client.get(f"/api/gap/analyses/{a['id']}/reproduce", headers=h).json()
    assert r["reproducible"] is False and "before inputs were versioned" in r["reason"]
