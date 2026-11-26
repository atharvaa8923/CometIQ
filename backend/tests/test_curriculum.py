"""Curriculum proposals (pull-request review), AACSB curriculum map, faculty-verified skill badges and outcomes."""
import io

PW = "CometIQ2026!"
SYL = """BUAN 6320 Database Foundations for Business Analytics
LEARNING OBJECTIVES
1. Design relational schemas for business data.
2. Write SQL queries with joins and aggregation.
Week 1: Relational modeling
Week 2: SQL joins lab (graded)
Week 3: SQL aggregation and window functions
Week 4: Data warehousing concepts
"""


def _login(client, email, pw=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _second_faculty(client):
    r = client.post("/api/auth/register", json={"email": "committee.member@utd.edu", "password": "Committee-Pass-1", "full_name": "Committee Member",
                                                 "role": "faculty", "join_code": "COMET-UTD", "accept_terms": True})
    if r.status_code in (200, 201):
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return _login(client, "committee.member@utd.edu", "Committee-Pass-1")


def test_proposal_review_adoption_badges_and_outcomes(client, tokens, monkeypatch):
    fac, adm, f2 = tokens["faculty"], tokens["admin"], _second_faculty(client)
    up = client.post("/api/gap/syllabi", headers=fac, data={"title": "Database Foundations", "code": "BUAN 6320", "semester": "Spring 2026",
                                                            "target": "Data Analyst"}, files={"file": ("s.txt", io.BytesIO(SYL.encode()), "text/plain")}).json()
    aid, sid = up["analysis_id"], up["syllabus_id"]
    a = client.get(f"/api/gap/analyses/{aid}", headers=fac).json()
    sk = {s["name"]: s["skill_id"] for s in a["skills"]}
    assert "SQL" in sk and "Python" in sk
    client.put(f"/api/gap/analyses/{aid}/reviews/{sk['SQL']}", headers=fac, json={"faculty_status": "practiced"})
    client.put(f"/api/gap/analyses/{aid}/reviews/{sk['Python']}", headers=fac, json={"faculty_status": "not_covered"})
    client.put(f"/api/gap/analyses/{aid}/decisions/{sk['Python']}", headers=fac, json={"decision": "add_here", "rationale": "Analyst postings expect Python for data prep."})
    t = client.post(f"/api/gap/syllabi/{sid}/decisions/draft", headers=fac).json()
    draft_id = client.get(f"/api/tasks/{t['task_id']}", headers=fac).json()["result"]["draft_id"]

    # ── proposal: diff, comments, reviews, revisions ──
    p = client.post("/api/curriculum/proposals", headers=fac, json={"syllabus_id": sid, "title": "Add Python data preparation to BUAN 6320",
                                                                    "summary": "Adds a Python lab and outcome.", "draft_id": draft_id}).json()
    assert p["status"] == "draft" and "PROPOSED CHANGES" in p["proposed_text"]
    assert {r["type"] for r in p["diff"]} <= {"equal", "insert"} and any(r["type"] == "insert" and "Python" in (r["right"] or "") for r in p["diff"])
    assert p["evidence"]["projected_score"] >= p["evidence"]["current_score"]
    assert all(x["id"] != p["id"] for x in client.get("/api/curriculum/proposals", headers=f2).json())   # drafts are private
    pid = p["id"]
    assert client.post(f"/api/curriculum/proposals/{pid}/submit", headers=fac).status_code == 400          # no effective term
    client.put(f"/api/curriculum/proposals/{pid}", headers=fac, json={"effective_term": "Fall 2027"})
    assert client.post(f"/api/curriculum/proposals/{pid}/submit", headers=f2).status_code == 403            # not the author
    assert client.post(f"/api/curriculum/proposals/{pid}/submit", headers=fac).json()["status"] == "in_review"
    assert client.post(f"/api/curriculum/proposals/{pid}/reviews", headers=fac, json={"vote": "approve"}).status_code == 403
    line = next(r["r"] for r in p["diff"] if r["type"] == "insert" and "Python" in (r["right"] or ""))
    assert client.post(f"/api/curriculum/proposals/{pid}/comments", headers=f2, json={"body": "nope", "anchor": "R99999"}).status_code == 400
    c = client.post(f"/api/curriculum/proposals/{pid}/comments", headers=f2, json={"body": "Which dataset will the lab use?", "anchor": f"R{line}"}).json()
    assert c["comments"][0]["anchor_text"] and "Python" in c["comments"][0]["anchor_text"]
    assert client.post(f"/api/curriculum/proposals/{pid}/reviews", headers=f2, json={"vote": "request_changes"}).status_code == 400
    r = client.post(f"/api/curriculum/proposals/{pid}/reviews", headers=f2, json={"vote": "request_changes", "body": "Name the dataset and the graded deliverable."}).json()
    assert r["status"] == "changes_requested"
    client.put(f"/api/curriculum/proposals/{pid}", headers=fac, json={"proposed_text": p["proposed_text"] + "\nPython lab dataset: city permits (graded notebook)."})
    r = client.post(f"/api/curriculum/proposals/{pid}/submit", headers=fac).json()
    assert r["revision"] == 2 and r["status"] == "in_review" and r["tally"]["changes_requested"] == 0
    assert client.post(f"/api/curriculum/proposals/{pid}/reviews", headers=f2, json={"vote": "approve", "body": "Thanks."}).json()["status"] == "in_review"
    r = client.post(f"/api/curriculum/proposals/{pid}/reviews", headers=adm, json={"vote": "approve"}).json()
    assert r["status"] == "approved" and r["tally"]["approvals"] == 2
    form = client.get(f"/api/curriculum/proposals/{pid}/change-request.json", headers=fac).json()
    assert form["course"]["code"] == "BUAN 6320" and len(form["approvals"]) == 2 and any("Python" in j for j in form["justification"])
    assert form["outcomes_current"] and form["proposal"]["effective_term"] == "Fall 2027"
    assert client.get(f"/api/curriculum/proposals/{pid}/change-request.pdf", headers=fac).content[:4] == b"%PDF"
    assert client.get(f"/api/curriculum/proposals/{pid}/change-request.docx", headers=fac).content[:2] == b"PK"
    assert client.post(f"/api/curriculum/proposals/{pid}/adopt", headers=f2, json={}).status_code == 403
    t = client.post(f"/api/curriculum/proposals/{pid}/adopt", headers=fac, json={}).json()
    assert client.get(f"/api/tasks/{t['task_id']}", headers=fac).json()["status"] == "done"
    p = client.get(f"/api/curriculum/proposals/{pid}", headers=fac).json()
    assert p["status"] == "adopted" and p["adopted_version_id"]
    hist = client.get(f"/api/gap/syllabi/{sid}/history", headers=fac).json()
    assert hist["versions"][-1]["semester"] == "Fall 2027" and "proposal" in hist["versions"][-1]["change_note"]
    dec = next(d for d in client.get(f"/api/gap/syllabi/{sid}/decisions", headers=fac).json()["active"] if d["skill"] == "Python")
    assert dec["status"] == "implemented"

    # ── curriculum map ──
    prog = next(x for x in client.get("/api/programs", headers=fac).json() if x["name"] == "Master of Science in Business Analytics and Artificial Intelligence")
    m = client.get(f"/api/curriculum/programs/{prog['id']}/map?target=Data Analyst", headers=fac).json()
    course = next(c for c in m["courses"] if c["code"] == "BUAN 6320")
    assert course["has_syllabus"] and m["summary"]
    ent = f"/api/curriculum/programs/{prog['id']}/map/{course['id']}/{sk['SQL']}"
    assert client.put(ent, headers=fac, json={"level": "M"}).status_code == 400
    assert client.put(ent, headers=fac, json={"level": "M", "rationale": "Graded SQL project assessed with the analytics rubric."}).status_code == 200
    m = client.get(f"/api/curriculum/programs/{prog['id']}/map?target=Data Analyst", headers=fac).json()
    cell = m["cells"][course["id"]][str(sk["SQL"])]
    assert cell["level"] == "M" and cell["source"] == "faculty map" and "BUAN 6320" in m["summary"][str(sk["SQL"])]["mastered_in"]
    assert client.get(f"/api/curriculum/programs/{prog['id']}/map.xlsx", headers=fac).content[:2] == b"PK"
    assert client.put(f"/api/curriculum/programs/{prog['id']}/map/nope/{sk['SQL']}", headers=fac, json={"level": "P"}).status_code == 404

    # ── badges: faculty basis × verified completion ──
    st = tokens["student"]
    ev = client.post("/api/evidence", headers=st, data={"kind": "course", "title": "BUAN 6320 Database Foundations", "course_id": course["id"],
                                                         "issued_on": "Spring 2026"}).json()
    assert client.get("/api/badges/mine", headers=st).json()["badges"] == [] or all(b["course_code"] != "BUAN 6320" for b in client.get("/api/badges/mine", headers=st).json()["badges"])
    client.post(f"/api/evidence/{ev['id']}/review", headers=tokens["advisor"], json={"decision": "verified"})
    mine = client.get("/api/badges/mine", headers=st).json()
    b = next(x for x in mine["badges"] if x["skill"] == "SQL" and x["course_code"] == "BUAN 6320")
    assert b["level"] == "mastered" and b["basis"]["confirmed_by"] and b["basis"]["completion_verified_by"] and b["term"] == "Spring 2026"
    assert client.get(f"/api/public/badges/{b['public_token']}").status_code == 404           # not shared yet
    client.put(f"/api/badges/{b['id']}/share", headers=st, json={"public": True})
    pub = client.get(f"/api/public/badges/{b['public_token']}").json()
    assert pub["valid"] and pub["skill"] == "SQL" and "confirms" in pub["statement"] and "public_token" not in pub
    me = client.get("/api/auth/me", headers=st).json()["id"]
    assert any(x["skill"] == "SQL" for x in client.get(f"/api/badges/student/{me}", headers=tokens["employer"]).json())
    t = client.get(f"/api/match/employer/talent?skills={sk['SQL']}&faculty_verified=true", headers=tokens["employer"]).json()
    hit = next(r for r in t["results"] if r["student"]["id"] == me)
    assert hit["skills"][0]["faculty_verified"] and "SQL" in hit["faculty_verified"]
    assert client.post(f"/api/badges/{b['id']}/revoke", headers=adm, json={"reason": "short"}).status_code == 422

    # ── outcomes (aggregate, suppressed below the minimum group size) ──
    o = client.get(f"/api/curriculum/decisions/{dec['id']}/outcomes", headers=fac).json()
    assert o["available"] and o["change_term"] == "Fall 2027" and o["before"]["suppressed"]
    monkeypatch.setattr(__import__("app.config", fromlist=["x"]).get_settings(), "OUTCOME_MIN_COHORT", 1)
    o = client.get(f"/api/curriculum/decisions/{dec['id']}/outcomes", headers=fac).json()
    assert o["before"]["students"] == 1 and o["before"]["badge_rate"] == 0.0 and o["after"]["suppressed"]
    allo = client.get("/api/curriculum/outcomes", headers=fac).json()
    assert any(x["decision_id"] == dec["id"] for x in allo["decisions"]) and any(s["skill"] == "SQL" for s in allo["supply"])
    assert client.get("/api/curriculum/outcomes", headers=st).status_code == 403
