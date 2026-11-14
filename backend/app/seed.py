"""Create tables and seed demo data (organization, users, catalog, skills, market jobs)."""
import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .data.sample_jobs import sample_jobs
from .data.taxonomy import SKILLS
from .db import Base, SessionLocal, engine
from .models import (
    Concentration, ConcentrationCourse, Course, CoursePrereq, CourseSkill, Organization, Program,
    ProgramCore, Skill, StudentCourse, StudentProfile, User,
)
from .security import hash_password
from .services import jobs as jobsvc
from .services import skills as sk

log = logging.getLogger("cometiq.seed")
DATA = Path(__file__).parent / "data"


def sync_skills(db: Session) -> None:
    existing = {s.name: s for s in db.scalars(select(Skill))}
    for name, cat, aliases, emerging in SKILLS:
        s = existing.get(name)
        if s:
            s.category, s.aliases, s.is_emerging = cat, aliases, emerging
        else:
            db.add(Skill(name=name, category=cat, aliases=aliases, is_emerging=emerging))
    db.flush()


def map_course_skills(db: Session, course: Course, ids: dict[str, int]) -> None:
    text = f"{course.title}. {course.title}. {course.description or ''}"  # title weighted x2
    found = sk.extract_builtin(text)
    course.skills.clear()
    db.flush()
    for name, info in found.items():
        if name in ids:
            in_title = name in sk.extract_builtin(course.title)
            course.skills.append(CourseSkill(skill_id=ids[name], weight=1.0 if in_title or info["mentions"] > 1 else 0.6))


def seed_catalog(db: Session, org: Organization) -> None:
    cat = json.loads((DATA / "catalog.json").read_text())
    ids = {s.name: s.id for s in db.scalars(select(Skill))}
    by_code: dict[str, Course] = {}
    for c in cat["courses"]:
        course = Course(org_id=org.id, code=c["code"], subject=c["subject"], title=c["title"],
                        credits=c["credits"] or 3, description=c["description"])
        db.add(course)
        by_code[c["code"]] = course
    db.flush()
    for course in by_code.values():
        map_course_skills(db, course, ids)
    for e in cat["prereqs"]:
        if e["course"] in by_code and e["requires"] in by_code:
            db.add(CoursePrereq(course_id=by_code[e["course"]].id, requires_id=by_code[e["requires"]].id, group=e["group"] or 0))
    for p in cat["programs"]:
        prog = Program(org_id=org.id, name=p["name"], type=p["type"], department=p["department"],
                       total_sch=p["total_sch"] or 0, core_sch=p["core_sch"] or 0, elective_sch=p["elective_sch"] or 0,
                       is_stem=bool(p["is_stem"]), catalog_url=p["catalog_url"], prereq_notes=p["prereq_notes"])
        for i, c in enumerate(p["core"] or []):
            if c["code"] in by_code:
                prog.core.append(ProgramCore(course_id=by_code[c["code"]].id, or_group=c["or_group"] or 0, sort=i))
        for cn in p["concentrations"] or []:
            conc = Concentration(name=cn["name"], required_sch=cn["required_sch"] or 0, notes=cn["notes"])
            for code in dict.fromkeys(cn["courses"] or []):
                if code in by_code:
                    conc.courses.append(ConcentrationCourse(course_id=by_code[code].id))
            prog.concentrations.append(conc)
        db.add(prog)
    db.flush()


def seed_demo(db: Session) -> None:
    s = get_settings()
    org = Organization(name="The University of Texas at Dallas", slug="utd", join_code="COMET-UTD")
    db.add(org)
    db.flush()
    pw = hash_password(s.DEMO_PASSWORD)
    users = {
        "admin": User(org_id=org.id, email="admin@cometiq.app", full_name="Avery Admin", role="admin", password_hash=pw),
        "faculty": User(org_id=org.id, email="faculty@cometiq.app", full_name="Dr. Morgan Lee", role="faculty", password_hash=pw),
        "student": User(org_id=org.id, email="student@cometiq.app", full_name="Jordan Rivera", role="student", password_hash=pw),
        "employer": User(org_id=org.id, email="employer@cometiq.app", full_name="Casey Nguyen", role="employer",
                         company="Lone Star Analytics", password_hash=pw),
    }
    db.add_all(users.values())
    db.flush()
    seed_catalog(db, org)
    for j in sample_jobs():
        jobsvc.upsert_job(db, {**j, "source": "seed"})
    # Demo student: MS Business Analytics & AI, two courses done
    prog = db.scalar(select(Program).where(Program.org_id == org.id, Program.name.like("%Business Analytics and Artificial Intelligence%")))
    db.add(StudentProfile(user_id=users["student"].id, program_id=prog.id if prog else None,
                          concentration_id=prog.concentrations[0].id if prog and prog.concentrations else None,
                          career_goal="Data Scientist", start_term="Fall 2026",
                          headline="MS Business Analytics & AI candidate"))
    if prog:
        for pc in prog.core[:2]:
            db.add(StudentCourse(user_id=users["student"].id, course_id=pc.course_id, status="completed", term="Fall 2026"))
    db.flush()
    seed_sample_syllabus(db, org, users["faculty"])


def seed_sample_syllabus(db: Session, org: Organization, owner: User) -> None:
    from .models import Syllabus, SyllabusSkill
    from .services import gap as gapsvc
    from .services import parser

    raw = (DATA / "samples" / "BUAN6356_syllabus.txt").read_text()
    course = db.scalar(select(Course).where(Course.org_id == org.id, Course.code == "BUAN 6356"))
    syl = Syllabus(org_id=org.id, owner_id=owner.id, course_id=course.id if course else None, code="BUAN 6356",
                   title="Business Analytics with R", semester="Spring 2026", filename="BUAN6356_syllabus.txt",
                   raw_text=raw, topics=parser.extract_topics(raw))
    db.add(syl)
    db.flush()
    found = sk.extract_builtin(raw)
    ids = sk.skill_ids(db, found)
    for name, info in found.items():
        syl.skills.append(SyllabusSkill(skill_id=ids[name], mentions=info["mentions"], evidence=info["evidence"]))
    db.flush()
    gapsvc.analyze(db, syl, "Data Analyst")


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_skills(db)
        if get_settings().SEED_DEMO and not db.scalar(select(func.count(Organization.id))):
            log.info("Seeding demo data…")
            seed_demo(db)
        db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Database ready.")
