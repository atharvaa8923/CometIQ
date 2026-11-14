"""Nebula full-catalog import and official-syllabus import (fixtures; no network)."""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Course, CoursePrereq
from app.services import nebula, syllabi

FIX = Path(__file__).parent / "fixtures"


def test_prereq_conversion():
    c = json.loads((FIX / "nebula_courses_sample.json").read_text())["data"]
    latest = nebula.latest_by_code(c)
    assert latest["CS 6375"]["title"] == "Machine Learning"               # newest catalog year wins
    code_of = {x["_id"]: f"{x['subject_prefix']} {x['course_number']}" for x in c}
    groups = nebula.prereq_groups(latest["CS 6375"]["prerequisites"], code_of)
    # required=2 of 3 options (one is a non-course 'major' requirement) → treated as OR over the course options
    assert groups == [["CS 5303", "OPRE 6301", "STAT 5351"]]
    allreq = {"type": "collection", "required": 2, "options": [{"type": "course", "class_reference": "c-cs1"},
              {"type": "collection", "required": 1, "options": [{"type": "course", "class_reference": "c-stat"}, {"type": "course", "class_reference": "c-opre"}]}]}
    assert nebula.prereq_groups(allreq, code_of) == [["CS 5303"], ["OPRE 6301", "STAT 5351"]]  # AND of (CS) and (STAT or OPRE)
    assert nebula.credits("3") == 3 and nebula.credits("") == 3 and nebula.credits("V") == 3


def test_catalog_import(client, tokens, monkeypatch):
    sample = json.loads((FIX / "nebula_courses_sample.json").read_text())
    monkeypatch.setattr(get_settings(), "NEBULA_API_KEY", "k")
    monkeypatch.setattr(nebula, "_get", lambda path, params=None: sample if path == "/course/all" else {"data": []})
    r = client.post("/api/admin/catalog/import-nebula?graduate_only=true", headers=tokens["admin"]).json()
    assert r["status"] == "done"
    res = r["result"]
    assert res["courses_in_nebula"] == 5 and res["added"] == 3  # 6 codes minus 1 undergrad; CS 5303, CS 6375, STAT 5351 are new
    with SessionLocal() as db:
        ml = db.scalar(select(Course).where(Course.code == "CS 6375"))
        assert ml.title == "Machine Learning" and any(cs.skill.name == "Machine Learning" for cs in ml.skills)
        reqs = {db.get(Course, e.requires_id).code for e in db.scalars(select(CoursePrereq).where(CoursePrereq.course_id == ml.id))}
        assert reqs == {"CS 5303", "STAT 5351", "OPRE 6301"}
        buan = db.scalar(select(Course).where(Course.code == "BUAN 6341"))
        curated = {db.get(Course, e.requires_id).code for e in db.scalars(select(CoursePrereq).where(CoursePrereq.course_id == buan.id))}
        assert "CS 5303" not in curated                                   # curated JSOM prerequisites are kept
        assert db.scalar(select(Course).where(Course.code == "CS 1336")) is None
    assert client.post("/api/admin/catalog/import-nebula", headers=tokens["faculty"]).status_code == 403


@pytest.mark.parametrize("url,ok", [
    ("https://dox.utdallas.edu/syl123456", True), ("https://utdallas.edu/a.pdf", True),
    ("http://dox.utdallas.edu/syl1", False), ("https://evil.com/utdallas.edu", False),
    ("https://utdallas.edu.evil.com/x", False), ("https://169.254.169.254/latest", False), ("file:///etc/passwd", False)])
def test_syllabus_url_allowlist(url, ok):
    assert syllabi.allowed_url(url) is ok


class _Resp:
    def __init__(self, content=b"", headers=None, status=200, location=None):
        self.content, self.headers, self.status_code = content, headers or {}, status
        self.is_redirect = location is not None
        self.next_request = type("R", (), {"url": location})() if location else None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _client_returning(*responses):
    seq = list(responses)

    class C:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return seq.pop(0)
    return C


def test_syllabus_import_end_to_end(client, tokens, monkeypatch):
    text = ("BUAN 6341 Applied Machine Learning syllabus. Week 1: Python and pandas. Week 2: regression. "
            "Week 3: machine learning with scikit-learn. Week 4: deep learning. Students build dashboards in Tableau. ") * 3
    monkeypatch.setattr(syllabi.httpx, "Client", _client_returning(_Resp(text.encode(), {"content-type": "text/plain"})))
    cid = client.get("/api/courses?q=BUAN 6341", headers=tokens["faculty"]).json()[0]["id"]
    bad = client.post("/api/gap/import-utd-syllabus", headers=tokens["faculty"], json={"course_id": cid, "url": "https://example.com/s.pdf"})
    assert bad.status_code == 400
    r = client.post("/api/gap/import-utd-syllabus", headers=tokens["faculty"],
                    json={"course_id": cid, "url": "https://dox.utdallas.edu/syl999", "term": "Fall 2025", "target": "Data Scientist"}).json()
    assert r["status"] == "done" and r["analysis_id"]
    a = client.get(f"/api/gap/analyses/{r['analysis_id']}", headers=tokens["faculty"]).json()
    assert a["syllabus"]["code"] == "BUAN 6341" and a["target"] == "Data Scientist"
    assert {"Python", "Machine Learning"} <= {s["name"] for s in a["skills"] if s["status"] != "missing"}


def test_syllabus_redirect_off_utd_is_blocked(monkeypatch):
    monkeypatch.setattr(syllabi.httpx, "Client", _client_returning(_Resp(location="https://attacker.example/x")))
    with pytest.raises(ValueError, match="not allowed"):
        syllabi.download("https://dox.utdallas.edu/syl1")
