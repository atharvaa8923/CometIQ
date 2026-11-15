"""Create tables and seed demo data (organization, users, catalog, skills, market jobs)."""
import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .data.sample_jobs import sample_jobs
from .data.taxonomy import SKILLS
from .db import SessionLocal
from .models import (
    Concentration, ConcentrationCourse, Course, CoursePrereq, Organization, Program,
    ProgramCore, Skill, StudentCourse, StudentProfile, User,
)
from .security import hash_password
from .services import jobs as jobsvc
from .services import skills as sk
from .services.seed_helpers import map_course_skills

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


def _catalog_year(url: str | None) -> str | None:
    import re

    m = re.search(r"/(20\d\d)/", url or "")
    return f"{m.group(1)}-{str(int(m.group(1)) + 1)[2:]}" if m else None


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
                       is_stem=bool(p["is_stem"]), catalog_url=p["catalog_url"], prereq_notes=p["prereq_notes"],
                       catalog_year=_catalog_year(p["catalog_url"]))
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
        "advisor": User(org_id=org.id, email="advisor@cometiq.app", full_name="Taylor Brooks", role="advisor", password_hash=pw),
    }
    from .routers.privacy import POLICY_VERSION

    for u in users.values():
        u.consent_version = POLICY_VERSION
    db.add_all(users.values())
    db.flush()
    seed_catalog(db, org)
    for j in sample_jobs():
        jobsvc.upsert_job(db, {**j, "source": "seed"})
    # Demo student: MS Business Analytics & AI, two courses done
    prog = db.scalar(select(Program).where(Program.org_id == org.id, Program.name.like("%Business Analytics and Artificial Intelligence%")))
    db.add(StudentProfile(user_id=users["student"].id, program_id=prog.id if prog else None,
                          concentration_id=next((c.id for c in prog.concentrations if "data science" in c.name.lower()),
                                                prog.concentrations[0].id if prog.concentrations else None) if prog else None,
                          career_goal="Data Scientist", start_term="Fall 2026",
                          headline="MS Business Analytics & AI candidate"))
    if prog:
        for pc in prog.core[:2]:
            db.add(StudentCourse(user_id=users["student"].id, course_id=pc.course_id, status="completed", term="Fall 2026"))
    db.flush()
    seed_sample_syllabus(db, org, users["faculty"])
    seed_match(db, org, users, pw)


def _demo_certificate(title: str, name: str) -> bytes:
    import io

    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(letter))
    w, h = landscape(letter)
    c.setStrokeColorRGB(0.05, 0.26, 0.19)
    c.setLineWidth(6)
    c.rect(30, 30, w - 60, h - 60)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w / 2, h - 150, "Certificate of Completion")
    c.setFont("Helvetica", 16)
    c.drawCentredString(w / 2, h - 200, "This certifies that")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w / 2, h - 240, name)
    c.setFont("Helvetica", 16)
    c.drawCentredString(w / 2, h - 280, f"has earned: {title}")
    c.setFont("Helvetica-Oblique", 11)
    c.setFillColorRGB(0.8, 0.2, 0.2)
    c.drawCentredString(w / 2, 70, "DEMO DOCUMENT generated by CometIQ seed data - not a real credential")
    c.save()
    return buf.getvalue()


def seed_evidence(db: Session, org: Organization, users: dict) -> None:
    """Pending demo evidence so the Verifications queue has something to review."""
    from .models import Evidence, EvidenceFile

    priya = db.scalar(select(User).where(User.email == "priya.shah@cometiq.app"))
    items = [
        (users["student"], "certification", "Tableau Desktop Specialist", "Tableau (Salesforce)",
         "Learned to connect data sources, build calculated fields, LOD expressions and interactive dashboards in Tableau; "
         "built a sales KPI dashboard with filters and parameters.", True),
        (priya, "certification", "AWS Certified Cloud Practitioner", "Amazon Web Services",
         "Covered core AWS services (EC2, S3, IAM), cloud computing concepts, cloud security and shared responsibility.", True),
        (users["student"], "project", "Customer churn prediction app", "Personal project",
         "Built a churn model in Python with scikit-learn (logistic regression, random forest) and deployed it as a REST API.", False),
    ]
    for u, kind, title, issuer, desc, has_file in items:
        if not u:
            continue
        found = sk.extract_builtin(f"{title}\n{desc}")
        e = Evidence(org_id=org.id, student_id=u.id, kind=kind, title=title, issuer=issuer, description=desc,
                     skills=sorted(sk.skill_ids(db, found).values()),
                     credential_url=None if has_file else "https://github.com/example/churn-app")
        if has_file:
            data = _demo_certificate(title, u.full_name)
            e.file = EvidenceFile(filename=f"{title.replace(' ', '_')}.pdf", content_type="application/pdf", size=len(data), data=data)
        db.add(e)


def seed_match(db: Session, org: Organization, users: dict, pw: str) -> None:
    from .data.sample_people import DEMO_STUDENT_RESUME, EMPLOYER_JOB, STUDENTS

    def set_resume(prof: StudentProfile, text: str) -> None:
        found = sk.extract_builtin(text)
        prof.resume_text, prof.resume_filename = text, "resume.txt"
        prof.resume_skills = sorted(sk.skill_ids(db, found).values())

    set_resume(db.get(StudentProfile, users["student"].id), DEMO_STUDENT_RESUME)
    courses = {c.code: c.id for c in db.scalars(select(Course).where(Course.org_id == org.id))}
    for st in STUDENTS:
        u = User(org_id=org.id, email=st["email"], full_name=st["name"], role="student", password_hash=pw)
        db.add(u)
        db.flush()
        prog = db.scalar(select(Program).where(Program.org_id == org.id, Program.name.like(f"%{st['program']}%")))
        conc = next((c.id for c in prog.concentrations if st["conc"] and st["conc"].lower() in c.name.lower()), None) if prog else None
        prof = StudentProfile(user_id=u.id, program_id=prog.id if prog else None, concentration_id=conc, career_goal=st["goal"],
                              headline=st["headline"])
        set_resume(prof, st["resume"])
        db.add(prof)
        for code in st["courses"]:
            if code in courses:
                db.add(StudentCourse(user_id=u.id, course_id=courses[code], status="completed", term="Fall 2026"))
    seed_evidence(db, org, users)
    jobsvc.upsert_job(db, {**EMPLOYER_JOB, "company": users["employer"].company, "source": "employer"},
                      org_id=org.id, employer_id=users["employer"].id)


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
        syl.skills.append(SyllabusSkill(skill_id=ids[name], mentions=info["mentions"], evidence=info["evidence"], excerpts=info.get("excerpts")))
    db.flush()
    gapsvc.analyze(db, syl, "Data Analyst")


def seed_production(db: Session) -> None:
    """Institution + full catalog, no demo users. The first admin comes from BOOTSTRAP_ADMIN_* variables."""
    import secrets

    s = get_settings()
    org = Organization(name=s.ORG_NAME, slug="utd" if "Dallas" in s.ORG_NAME else "main",
                       join_code=(s.ORG_JOIN_CODE or f"COMET-{secrets.token_hex(3).upper()}").upper())
    db.add(org)
    db.flush()
    seed_catalog(db, org)
    if s.BOOTSTRAP_ADMIN_EMAIL and len(s.BOOTSTRAP_ADMIN_PASSWORD) >= 12:
        db.add(User(org_id=org.id, email=s.BOOTSTRAP_ADMIN_EMAIL.lower(), full_name="Administrator", role="admin",
                    password_hash=hash_password(s.BOOTSTRAP_ADMIN_PASSWORD)))
        log.info("Created bootstrap admin %s", s.BOOTSTRAP_ADMIN_EMAIL)
    else:
        log.warning("No bootstrap admin: set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD (12+ chars) and restart.")
    log.info("Organization %s ready — join code %s", org.name, org.join_code)


def ensure_bootstrap_admin(db: Session) -> None:
    s = get_settings()
    if not s.BOOTSTRAP_ADMIN_EMAIL or len(s.BOOTSTRAP_ADMIN_PASSWORD) < 12:
        return
    db.flush()  # the session doesn't autoflush: make an admin created by seed_production visible
    if db.scalar(select(User.id).where(func.lower(User.email) == s.BOOTSTRAP_ADMIN_EMAIL.lower())):
        return
    org = db.scalar(select(Organization).order_by(Organization.created_at))
    # demo admins (@cometiq.app) don't count: a pilot environment started from demo data still gets its real admin
    if org and not db.scalar(select(User.id).where(User.org_id == org.id, User.role == "admin", ~User.email.like("%@cometiq.app"))):
        db.add(User(org_id=org.id, email=s.BOOTSTRAP_ADMIN_EMAIL.lower(), full_name="Administrator", role="admin",
                    password_hash=hash_password(s.BOOTSTRAP_ADMIN_PASSWORD)))


def init_db() -> None:
    from .migrate import migrate

    migrate()
    with SessionLocal() as db:
        sync_skills(db)
        if not db.scalar(select(func.count(Organization.id))):
            if get_settings().SEED_DEMO:
                log.info("Seeding demo data…")
                seed_demo(db)
            else:
                log.info("Seeding institution and catalog (production mode)…")
                seed_production(db)
        ensure_bootstrap_admin(db)
        db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Database ready.")
