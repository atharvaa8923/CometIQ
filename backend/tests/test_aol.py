"""AACSB assurance-of-learning report: goals, results, closing the loop, exports."""
import io

from sqlalchemy import select

from app.db import SessionLocal

BAAI = "Master of Science in Business Analytics and Artificial Intelligence"


def _program(client, h):
    sc = client.get("/api/curriculum/scorecard", headers=h).json()
    return next(p["id"] for p in sc["programs"] if p["name"] == BAAI)


def test_goals_results_and_report(client, tokens):
    from app.models import Skill

    fac = tokens["faculty"]
    pid = _program(client, fac)
    sug = client.get(f"/api/curriculum/programs/{pid}/aol/suggestions", headers=fac).json()
    assert sug and all(s["skills"] for s in sug)
    with SessionLocal() as db:
        ids = dict(db.execute(select(Skill.name, Skill.id).where(Skill.name.in_(["SQL", "Python", "Tableau", "Machine Learning"]))).all())
    base = f"/api/curriculum/programs/{pid}/aol"
    g1 = client.post(f"{base}/goals", headers=fac, json={"code": "lg1", "title": "Graduates manage and query business data",
                                                         "skill_ids": [ids["SQL"], ids["Python"]], "target_pct": 80}).json()
    assert g1["code"] == "LG1" and {s["name"] for s in g1["skills"]} == {"SQL", "Python"}
    assert client.post(f"{base}/goals", headers=fac, json={"code": "LG1", "title": "Duplicate goal code", "skill_ids": []}).status_code == 409
    assert client.post(f"{base}/goals", headers=fac, json={"code": "LG9", "title": "Unknown skill here", "skill_ids": [999999]}).status_code == 400
    g2 = client.post(f"{base}/goals", headers=fac, json={"code": "LG2", "title": "Graduates communicate insights visually",
                                                         "skill_ids": [ids["Tableau"]], "target_pct": 75}).json()

    # results: below target with an action, then met the next term
    r = client.post(f"{base}/goals/{g1['id']}/results", headers=fac, json={"term": "Spring 2026", "course_code": "buan 6320",
        "measure": "Final project rubric: query design", "students_assessed": 40, "students_meeting": 28,
        "action": "Added a graded SQL window-functions lab in Fall 2026"}).json()
    assert r["met_pct"] == 70.0 and not r["met_target"] and r["course_code"] == "BUAN 6320" and r["target_pct"] == 80
    client.post(f"{base}/goals/{g1['id']}/results", headers=fac, json={"term": "Fall 2026", "course_code": "BUAN 6320",
        "measure": "Final project rubric: query design", "students_assessed": 42, "students_meeting": 37})
    bad = client.post(f"{base}/goals/{g1['id']}/results", headers=fac, json={"term": "Fall 2026", "measure": "x" * 5, "students_assessed": 5, "students_meeting": 9})
    assert bad.status_code == 400
    assert client.post(f"{base}/goals/{g1['id']}/results", headers=fac, json={"term": "Fall 2026", "measure": "Exit survey",
        "measure_type": "opinion", "students_assessed": 5, "students_meeting": 4}).status_code == 422

    rep = client.get(base, headers=fac).json()
    goals = {g["code"]: g for g in rep["goals"]}
    lg1 = goals["LG1"]
    assert lg1["status"] == "met" and lg1["results"][0]["term"] == "Fall 2026"          # latest term first
    assert any(i["kind"] == "assessment action" and "window-functions" in i["action"] for i in lg1["closing_the_loop"])
    assert set(lg1["coverage"]) == {"introduced_in", "practiced_in", "mastered_in", "verified_in"}
    assert goals["LG2"]["status"] in ("not_assessed", "gap") and rep["summary"]["goals"] == 2
    assert rep["summary"]["terms_assessed"] == ["Spring 2026", "Fall 2026"] and rep["summary"]["met"] == 1

    # exports
    d = client.get(f"{base}/report.docx", headers=fac)
    assert d.status_code == 200 and d.content[:2] == b"PK"
    from docx import Document

    text = "\n".join(p.text for p in Document(io.BytesIO(d.content)).paragraphs)
    assert "Assurance of Learning Report" in text and "LG1: Graduates manage and query business data" in text and "window-functions" in text
    pdf = client.get(f"{base}/report.pdf", headers=fac)
    assert pdf.content[:4] == b"%PDF"
    assert client.get(f"{base}/report.txt", headers=fac).status_code == 404

    # edit, delete, permissions
    up = client.put(f"{base}/goals/{g2['id']}", headers=fac, json={"code": "LG2", "title": "Graduates communicate data visually",
                                                                   "skill_ids": [ids["Tableau"], ids["Machine Learning"]], "target_pct": 70}).json()
    assert up["target_pct"] == 70 and len(up["skills"]) == 2
    assert client.get(base, headers=tokens["student"]).status_code == 403
    assert client.delete(f"{base}/goals/{g2['id']}", headers=fac).json() == {"deleted": g2["id"]}
    assert client.delete(f"{base}/goals/{g2['id']}", headers=fac).status_code == 404


def test_graded_work_is_listed_as_direct_measures(client, tokens, monkeypatch):
    """A course imported from Canvas contributes its graded assignments and rubric criteria as direct measures."""
    import httpx

    from app import integrations
    from app.config import get_settings
    from app.models import Skill
    from test_institution import FakeCanvas, _connect_canvas

    canvas = FakeCanvas()
    monkeypatch.setattr(integrations, "_transport", httpx.MockTransport(lambda req: canvas(req)))
    for k, v in {"CANVAS_BASE_URL": "https://canvas.test", "CANVAS_CLIENT_ID": "1", "CANVAS_CLIENT_SECRET": "x"}.items():
        monkeypatch.setattr(get_settings(), k, v)
    fac = tokens["faculty"]
    _connect_canvas(client, fac)
    client.post("/api/canvas/courses/101/import", headers=fac, json={})
    pid = _program(client, fac)
    with SessionLocal() as db:
        tid = db.scalar(select(Skill.id).where(Skill.name == "Tableau"))
    base = f"/api/curriculum/programs/{pid}/aol"
    g = client.post(f"{base}/goals", headers=fac, json={"code": "LG7", "title": "Graduates build dashboards", "skill_ids": [tid]}).json()
    lg = next(x for x in client.get(base, headers=fac).json()["goals"] if x["id"] == g["id"])
    m = lg["skills_detail"][0]["measures"]
    assert any(x["course"] == "BUAN 6320" and x["assignment"] == "Project 1: Tableau dashboard" and x["course_grade_share"] == 1.0 for x in m)
    assert lg["direct_measures"] >= 1
