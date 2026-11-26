"""Backend performance profile at realistic scale.

Seeds a scaled dataset on top of the demo data (students with courses and verified evidence, many job postings, analyzed syllabi
with reviews and decisions), then calls every key endpoint several times and reports median / p95 latency and the number of SQL
queries per request. Run against a scratch database only:

  DATABASE_URL=sqlite:////tmp/perf.db python scripts/perf_profile.py [--students 1500 --jobs 400 --syllabi 40] [--json out.json]
"""
import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("JOB_SYNC_ENABLED", "false")
os.environ.setdefault("TASKS_INLINE", "true")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "perf-secret-perf-secret-perf-secret-42")
os.environ.setdefault("LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logging  # noqa: E402

logging.disable(logging.INFO)

from sqlalchemy import event, func, select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402

QUERIES = {"n": 0}


@event.listens_for(engine, "before_cursor_execute")
def _count(*_a, **_k):
    QUERIES["n"] += 1


def seed(n_students: int, n_jobs: int, n_syllabi: int) -> None:
    from app.models import (Course, Evidence, GapReview, Job, Organization, Program, StudentCourse, StudentProfile, Syllabus, User)
    from app.routers.gap import run_analysis
    from app.security import hash_password
    from app.services import badges as badgesvc
    from app.services import jobs as jobsvc
    from app.services.curriculum_map import program_courses

    rnd = random.Random(7)
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User).where(User.email.like("perf.%"))):
            return
        org = db.scalar(select(Organization))
        pw = hash_password("Perf-Student-1")
        progs = list(db.scalars(select(Program).where(Program.org_id == org.id)))
        baai = next(p for p in progs if "Business Analytics and Artificial" in p.name)
        pcourses = [c for c, _ in program_courses(baai)]
        all_courses = list(db.scalars(select(Course).where(Course.org_id == org.id)))
        # job postings: variations of the seed postings with the same skills
        base = list(db.scalars(select(Job).where(Job.source == "seed")))
        for i in range(n_jobs):
            j = rnd.choice(base)
            jobsvc.upsert_job(db, {"title": f"{j.title} {i}", "company": j.company, "location": j.location, "role_family": j.role_family,
                                   "description": j.description or "", "source": "csv", "external_id": f"perf-{i}"},
                              org_id=None, skills_override={s.skill.name: s.importance for s in j.skills})
        db.flush()
        # students
        terms = ["Fall 2025", "Spring 2026", "Fall 2026", "Spring 2027"]
        for i in range(n_students):
            u = User(org_id=org.id, email=f"perf.student{i}@utd.edu", full_name=f"Perf Student {i}", role="student", password_hash=pw)
            db.add(u)
            db.flush()
            db.add(StudentProfile(user_id=u.id, program_id=baai.id if rnd.random() < 0.6 else rnd.choice(progs).id,
                                  career_goal=rnd.choice(["Data Analyst", "Data Scientist", "Business Analyst", None]), open_to_match=rnd.random() < 0.8))
            for c in rnd.sample(pcourses, k=min(len(pcourses), rnd.randint(3, 8))):
                st = rnd.choice(["completed", "completed", "enrolled", "planned"])
                db.add(StudentCourse(user_id=u.id, course_id=c.id, status=st, term=rnd.choice(terms)))
                if st == "completed" and rnd.random() < 0.3:
                    db.add(Evidence(org_id=org.id, student_id=u.id, kind="course", title=c.code, course_id=c.id, status="verified",
                                    issued_on=rnd.choice(terms[:2]), skills=[]))
            if i % 200 == 0:
                db.flush()
        db.commit()
        fac = db.scalar(select(User).where(User.email == "faculty@cometiq.app"))
        # analyzed syllabi for program courses (and some others)
        made = 0
        for c in (pcourses + all_courses):
            if made >= n_syllabi:
                break
            if db.scalar(select(Syllabus.id).where(Syllabus.code == c.code)):
                continue
            text = f"{c.code} {c.title}\n{c.description or ''}\n" + "\n".join(f"Week {w}: {t}" for w, t in enumerate(
                rnd.sample(["SQL joins lab", "Python pandas lab", "Excel modeling", "Tableau dashboards", "Regression analysis",
                            "Machine learning basics", "Statistics review", "Data cleaning", "Forecasting", "Optimization"], 5), 1))
            syl = Syllabus(org_id=org.id, owner_id=fac.id, course_id=c.id, code=c.code, title=c.title, semester="Spring 2026", raw_text=text, topics=[])
            db.add(syl)
            db.commit()
            run_analysis(db, syl.id, "Data Analyst", extract=True, user_id=fac.id)
            ga = db.get(Syllabus, syl.id).analyses[0]
            for row in ga.result["skills"][:6]:
                db.add(GapReview(analysis_id=ga.id, skill_id=row["skill_id"], reviewer_id=fac.id, system_status=row["status"],
                                 faculty_status="practiced" if row["status"] == "covered" else "not_covered",
                                 decision="confirmed"))
            db.commit()
            made += 1
        badgesvc.sync(db, org.id)
        db.commit()


def measure(runs: int) -> list[dict]:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import Job, Program, Skill, Syllabus

    out = []
    with TestClient(app) as c:
        tok = {r: {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": f"{r}@cometiq.app", "password": "CometIQ2026!"}).json()["token"]}
               for r in ("faculty", "student", "employer", "admin")}
        with SessionLocal() as db:
            syl = db.scalar(select(Syllabus).where(Syllabus.code == "BUAN 6356"))
            aid = syl.analyses[0].id
            text = syl.raw_text + "\nWeek 15: SQL joins lab (graded)"
            pid = db.scalar(select(Program.id).where(Program.name.like("%Business Analytics and Artificial%")))
            sql = db.scalar(select(Skill.id).where(Skill.name == "SQL"))
            py = db.scalar(select(Skill.id).where(Skill.name == "Python"))
            emp_job = db.scalar(select(Job.id).where(Job.source == "employer"))
        calls = [
            ("faculty", "GET", "/api/gap/syllabi", None), ("faculty", "GET", f"/api/gap/analyses/{aid}", None),
            ("faculty", "GET", f"/api/gap/syllabi/{syl.id}/history", None), ("faculty", "GET", "/api/gap/market?target=Data Analyst", None),
            ("faculty", "GET", f"/api/gap/programs/{pid}?target=Data Analyst", None),
            ("faculty", "POST", "/api/gap/copilot/preview", {"syllabus_id": syl.id, "text": text}),
            ("faculty", "GET", f"/api/curriculum/programs/{pid}/map", None), ("faculty", "GET", "/api/curriculum/scorecard", None),
            ("faculty", "POST", f"/api/curriculum/programs/{pid}/simulate", {"ops": []}), ("faculty", "GET", "/api/curriculum/outcomes", None),
            ("faculty", "POST", "/api/ask", {"question": "Which priority gaps have no decision yet?"}),
            ("faculty", "POST", "/api/ask", {"question": "Where is SQL practiced?"}),
            ("faculty", "GET", "/api/graph/map", None),
            ("student", "GET", "/api/match/jobs", None), ("student", "GET", "/api/path/overview", None),
            ("student", "GET", "/api/path/recommendations", None), ("student", "POST", "/api/path/plan", {}),
            ("student", "GET", "/api/badges/mine", None), ("student", "GET", "/api/stacks", None), ("student", "GET", "/api/match/learn-next", None),
            ("employer", "GET", f"/api/match/employer/talent?skills={sql},{py}", None),
            ("employer", "GET", f"/api/match/employer/jobs/{emp_job}/candidates", None),
            ("admin", "GET", "/api/dashboard/summary", None), ("admin", "GET", "/api/dashboard/impact", None),
        ]
        for role, method, path, body in calls:
            times, qs, status = [], [], None
            for _ in range(runs):
                QUERIES["n"] = 0
                t = time.perf_counter()
                r = c.request(method, path, headers=tok[role], json=body)
                times.append((time.perf_counter() - t) * 1000)
                qs.append(QUERIES["n"])
                status = r.status_code
            times.sort()
            out.append({"endpoint": f"{method} {path.split('?')[0]}", "role": role, "status": status,
                        "median_ms": round(statistics.median(times), 1), "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)], 1),
                        "queries": int(statistics.median(qs))})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=1500)
    ap.add_argument("--jobs", type=int, default=400)
    ap.add_argument("--syllabi", type=int, default=40)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--json")
    a = ap.parse_args()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app):
        pass  # runs migrations and the demo seed
    t = time.time()
    seed(a.students, a.jobs, a.syllabi)
    print(f"seeded in {time.time() - t:.0f}s")
    rows = measure(a.runs)
    w = max(len(r["endpoint"]) for r in rows)
    print(f"{'endpoint':{w}}  role      status  median ms  p95 ms  queries")
    for r in sorted(rows, key=lambda r: -r["median_ms"]):
        print(f"{r['endpoint'][:w]:{w}}  {r['role']:8}  {r['status']:6}  {r['median_ms']:9}  {r['p95_ms']:6}  {r['queries']:7}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
