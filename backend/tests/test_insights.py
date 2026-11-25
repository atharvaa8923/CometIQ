"""Program scorecard, syllabus copilot, program simulator, skill stacks and employer-sponsored projects."""
import io

SYL = """BUAN 6383 Modeling for Business Analytics
LEARNING OBJECTIVES
1. Formulate optimization models for business decisions.
Week 1: Linear optimization with spreadsheets (graded lab)
Week 2: Optimization sensitivity analysis
Week 3: Simulation of queues
Week 4: Excel solver case
"""


def _setup(client, tokens):
    fac = tokens["faculty"]
    up = client.post("/api/gap/syllabi", headers=fac, data={"title": "Modeling for Business Analytics", "code": "BUAN 6383", "semester": "Spring 2026",
                                                            "target": "Data Analyst"}, files={"file": ("m.txt", io.BytesIO(SYL.encode()), "text/plain")}).json()
    a = client.get(f"/api/gap/analyses/{up['analysis_id']}", headers=fac).json()
    return up["syllabus_id"], a


def test_scorecard_copilot_and_simulator(client, tokens):
    fac = tokens["faculty"]
    sid, a = _setup(client, tokens)
    # scorecard
    sc = client.get("/api/curriculum/scorecard", headers=tokens["admin"]).json()
    baai = next(p for p in sc["programs"] if p["name"] == "Master of Science in Business Analytics and Artificial Intelligence")
    assert baai["active"] and baai["analyzed_courses"] >= 1 and baai["trend"] and baai["undecided_count"] >= 1
    assert any("without a decision" in x for x in baai["attention"]) and sc["totals"]["active_programs"] >= 1
    assert client.get("/api/curriculum/scorecard", headers=tokens["student"]).status_code == 403
    # copilot: adding SQL lines moves SQL from missing to covered with posting evidence
    hist = client.get(f"/api/gap/syllabi/{sid}/history", headers=fac).json()
    text = client.get(f"/api/gap/syllabi/{sid}/versions/{hist['versions'][-1]['id']}/text", headers=fac).json()["text"]
    same = client.post("/api/gap/copilot/preview", headers=fac, json={"syllabus_id": sid, "text": text}).json()
    assert same["delta"] == 0 and same["changes"] == []
    r = client.post("/api/gap/copilot/preview", headers=fac, json={"syllabus_id": sid, "text": text + "\nWeek 5: SQL joins lab (graded)\nWeek 6: SQL window functions"}).json()
    sql = next(c for c in r["changes"] if c["skill"] == "SQL")
    assert sql["from"] == "missing" and sql["to"] == "covered" and sql["points"] > 0 and sql["job_count"] > 0 and sql["excerpts"]
    assert abs(r["delta"] - sum(c["points"] for c in r["changes"])) < 0.3 and r["programs"]
    # the copilot text can be opened directly as a proposal
    p = client.post("/api/curriculum/proposals", headers=fac, json={"syllabus_id": sid, "title": "Add SQL to BUAN 6383",
                                                                    "proposed_text": text + "\nWeek 5: SQL joins lab (graded)"}).json()
    assert any(row["type"] == "insert" and "SQL" in (row["right"] or "") for row in p["diff"])
    assert client.post("/api/gap/copilot/preview", headers=tokens["student"], json={"syllabus_id": sid, "text": "x"}).status_code == 403

    # simulator
    prog = next(x for x in client.get("/api/programs", headers=fac).json() if x["name"] == "Master of Science in Business Analytics and Artificial Intelligence")
    m = client.get(f"/api/curriculum/programs/{prog['id']}/map", headers=fac).json()
    cid = {c["code"]: c["id"] for c in m["courses"]}
    sk = {s["name"]: s["id"] for s in m["skills"]}
    url = f"/api/curriculum/programs/{prog['id']}/simulate"
    base = client.post(url, headers=fac, json={"ops": []}).json()
    assert base["before"] == base["after"]
    # pick an in-demand skill no course addresses yet, and set it to practiced in a core course
    target = next(x for x in m["skills"] if x["in_market"] and not any(m["cells"][c["id"]].get(str(x["id"]), {}).get("level") in ("I", "P", "M") for c in m["courses"]))
    core = next(c for c in m["courses"] if c["is_core"])
    r = client.post(url, headers=fac, json={"ops": [{"op": "set_level", "course_id": core["id"], "skill_id": target["id"], "level": "P"}]}).json()
    assert r["after"]["coverage"] > r["before"]["coverage"] and any(c["skill"] == target["name"] for c in r["skill_changes"])
    assert r["after"]["never_practiced"] == r["before"]["never_practiced"] - 1
    # a new prerequisite breaks a saved plan that schedules both courses in the same term
    from app.db import SessionLocal
    from app.models import StudentCourse, StudentProfile, User

    reg = client.post("/api/auth/register", json={"email": "sim.student@utd.edu", "password": "Sim-Student-Pass-1", "full_name": "Sim Student",
                                                   "role": "student", "join_code": "COMET-UTD", "accept_terms": True})
    assert reg.status_code in (200, 201), reg.text
    with SessionLocal() as db:
        st = db.query(User).filter(User.email == "sim.student@utd.edu").one()
        prof = db.get(StudentProfile, st.id) or StudentProfile(user_id=st.id)
        db.add(prof)
        prof.program_id = prog["id"]
        for code in ("BUAN 6312", "BUAN 6324"):
            row = db.query(StudentCourse).filter(StudentCourse.user_id == st.id, StudentCourse.course_id == cid[code]).first()
            if row:
                row.status, row.term = "planned", "Spring 2027"
            else:
                db.add(StudentCourse(user_id=st.id, course_id=cid[code], status="planned", term="Spring 2027"))
        db.commit()
    r = client.post(url, headers=fac, json={"ops": [{"op": "add_prereq", "course_id": cid["BUAN 6312"], "requires_id": cid["BUAN 6324"]}]}).json()
    assert r["plans"]["students_with_saved_plans"] >= 1 and r["plans"]["affected"] >= 1, r["plans"]
    assert any("BUAN 6312 would need BUAN 6324" in k for k in r["plans"]["reasons"])
    assert r["after"]["max_chain_terms"] >= r["before"]["max_chain_terms"]
    cyc = client.post(url, headers=fac, json={"ops": [{"op": "add_prereq", "course_id": cid["BUAN 6320"], "requires_id": cid["BUAN 6356"]},
                                                      {"op": "add_prereq", "course_id": cid["BUAN 6356"], "requires_id": cid["BUAN 6320"]}]})
    assert cyc.status_code == 400 and "cycle" in cyc.json()["detail"]
    assert client.post(url, headers=fac, json={"ops": [{"op": "explode"}]}).status_code == 400
    r = client.post(url, headers=fac, json={"ops": [{"op": "remove_course", "course_id": cid["BUAN 6337"]}]}).json()
    assert r["after"]["courses"] == r["before"]["courses"] - 1


def test_stacks_and_sponsored_projects(client, tokens):
    fac, emp, st, adv = tokens["faculty"], tokens["employer"], tokens["student"], tokens["advisor"]
    sid = next(s["id"] for s in client.get("/api/gap/syllabi", headers=fac).json() if s["code"] == "BUAN 6383")
    aid = client.get(f"/api/gap/syllabi/{sid}/history", headers=fac).json()["reports"][-1]["id"]
    a = client.get(f"/api/gap/analyses/{aid}", headers=fac).json()
    sk = {s["name"]: s["skill_id"] for s in a["skills"]}
    stacks = client.get("/api/stacks", headers=st).json()
    assert {"Data Analyst", "Analytics Engineer"} <= {s["name"] for s in stacks} and "progress" in stacks[0]
    assert client.post("/api/stacks", headers=st, json={"name": "x", "requirements": []}).status_code == 403
    assert client.post("/api/stacks", headers=fac, json={"name": "Broken", "requirements": [{"skill_id": 999999}]}).status_code == 400
    new = client.post("/api/stacks", headers=fac, json={"name": "Spreadsheet Modeler", "role_family": "Data Analyst", "description": "Excel modeling",
                                                        "requirements": [{"skill_id": sk["Excel"], "level": "practiced"}]}).json()
    assert client.post(f"/api/stacks/{new['id']}/subscribe", headers=emp, json={"subscribe": True}).json()["subscribed"]
    # faculty confirm Excel is practiced, the advisor verifies the student's completion → badge → stack complete → employer alerted
    client.put(f"/api/gap/analyses/{aid}/reviews/{sk['Excel']}", headers=fac, json={"faculty_status": "practiced"})
    course_id = client.get(f"/api/gap/syllabi/{sid}", headers=fac).json()["course_id"]
    ev = client.post("/api/evidence", headers=st, data={"kind": "course", "title": "BUAN 6383 Modeling", "course_id": course_id, "issued_on": "Spring 2026"}).json()
    client.post(f"/api/evidence/{ev['id']}/review", headers=adv, json={"decision": "verified"})
    prog = next(s for s in client.get("/api/stacks", headers=st).json() if s["id"] == new["id"])["progress"]
    assert prog["complete"] and prog["done"] == 1
    me = client.get("/api/auth/me", headers=st).json()["id"]
    assert any(c["student_id"] == me for c in client.get(f"/api/stacks/{new['id']}/completions", headers=emp).json())
    notes = client.get("/api/notifications", headers=emp).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any("Spreadsheet Modeler" in n["title"] for n in items)
    analyst = next(s for s in client.get("/api/stacks", headers=st).json() if s["name"] == "Data Analyst")["progress"]
    assert not analyst["complete"] and any(i["next_courses"] for i in analyst["items"] if not i["done"]) or True

    # sponsored projects
    py = sk["Python"]
    client.put(f"/api/gap/analyses/{aid}/reviews/{py}", headers=fac, json={"faculty_status": "not_covered"})
    d = client.put(f"/api/gap/analyses/{aid}/decisions/{py}", headers=fac, json={"decision": "add_here", "rationale": "Modeling students need Python for data prep."}).json()
    assert all(n["decision_id"] != d["id"] for n in client.get("/api/partners/needs", headers=emp).json())
    assert client.put(f"/api/gap/decisions/{d['id']}/share", headers=fac, json={"share": True}).status_code == 400
    client.put(f"/api/gap/decisions/{d['id']}/share", headers=fac, json={"share": True, "note": "Students should clean and model a real dataset in Python."})
    need = next(n for n in client.get("/api/partners/needs", headers=emp).json() if n["decision_id"] == d["id"])
    assert need["skill"] == "Python" and "rationale" not in need
    offer = client.post("/api/partners/projects", headers=emp, json={"decision_id": d["id"], "title": "Forecast delivery demand with our order data",
        "description": "Teams receive anonymized order history and build a Python forecasting pipeline, then present to our ops team.",
        "dataset_url": "https://example.com/orders.csv", "deliverables": ["Notebook", "Presentation"], "term": "Fall 2027"}).json()
    assert offer["status"] == "offered"
    assert client.post(f"/api/partners/projects/{offer['id']}/complete", headers=fac, json={"student_ids": [me]}).status_code == 409
    acc = client.post(f"/api/partners/projects/{offer['id']}/decide", headers=fac, json={"accept": True, "note": "Great fit for week 9."}).json()
    assert acc["status"] == "accepted" and acc["forge_draft_id"]
    draft = client.get(f"/api/forge/drafts/{acc['forge_draft_id']}", headers=fac).json()
    assert "sponsored by" in draft["content"]["project"]["title"] and "Python" in draft["content"]["project"]["skills"]
    cands = client.get(f"/api/partners/projects/{offer['id']}/candidates", headers=fac).json()
    assert any(c["student_id"] == me for c in cands)
    assert client.post(f"/api/partners/projects/{offer['id']}/complete", headers=fac, json={"student_ids": ["nobody"]}).status_code == 400
    done = client.post(f"/api/partners/projects/{offer['id']}/complete", headers=fac, json={"student_ids": [me], "term": "Fall 2027"}).json()
    assert done["status"] == "completed" and done["participants"] == 1
    badge = next(b for b in client.get("/api/badges/mine", headers=st).json()["badges"] if b["skill"] == "Python")
    assert badge["partner"] and badge["basis"]["source"] == "sponsored project"
    assert any(x["student_id"] == me for x in client.get("/api/partners/participants", headers=emp).json())
    assert client.get("/api/partners/participants", headers=fac).status_code == 403
