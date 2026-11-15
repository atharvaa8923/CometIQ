"""Background task handlers (imported by the worker)."""
from sqlalchemy.orm import Session

from ..models import Task
from . import email as mail
from .tasks import handler


@handler("email.send")
def send_email(db: Session, task: Task) -> dict:
    p = task.payload
    html_body, text = mail.render(p["title"], p.get("paragraphs", []), p.get("cta"), p.get("url"))
    mail.send(p["to"], p.get("subject") or p["title"], html_body, text)
    return {"sent_to": p["to"]}


@handler("gap.analyze")
def gap_analyze(db: Session, task: Task) -> dict:
    from ..routers.gap import run_analysis

    p = task.payload
    return run_analysis(db, p["syllabus_id"], p.get("target", "auto"), p.get("top_n", 30), p.get("extract", False), task,
                        sample_id=p.get("sample_id"), user_id=task.user_id, change_note=p.get("change_note"),
                        proposal_id=p.get("proposal_id"))


@handler("forge.generate")
def forge_generate(db: Session, task: Task) -> dict:
    from ..models import User
    from ..routers.forge import GenerateIn, run_generate

    p = dict(task.payload)
    user = db.get(User, p.pop("user_id"))
    return run_generate(db, user, GenerateIn(**p), task)


@handler("catalog.nebula_import")
def nebula_catalog_import(db: Session, task: Task) -> dict:
    from sqlalchemy import select

    from ..models import Course, CoursePrereq, Skill
    from . import nebula
    from .seed_helpers import map_course_skills
    from .tasks import set_progress

    org_id, graduate_only = task.org_id, task.payload.get("graduate_only", False)
    set_progress(db, task, "Downloading the UTD catalog from Nebula…")
    raw = nebula.fetch_all_courses(lambda m: set_progress(db, task, m))
    latest = nebula.latest_by_code(raw)
    if graduate_only:
        latest = {k: v for k, v in latest.items() if (v.get("class_level") or "").lower().startswith("grad") or k.split()[-1][:1] in "5678"}
    code_of = {str(c.get("_id")): code for code, c in latest.items()}
    for c in raw:  # older catalog-year records referenced by prerequisites map to the same code
        code = f"{(c.get('subject_prefix') or '').upper()} {(c.get('course_number') or '').strip()}"
        if code in latest:
            code_of.setdefault(str(c.get("_id")), code)
    existing = {c.code: c for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    ids = {s.name: s.id for s in db.scalars(select(Skill))}
    added = updated = 0
    for i, (code, nc) in enumerate(sorted(latest.items())):
        c = existing.get(code)
        title, desc = (nc.get("title") or "").strip() or code, (nc.get("description") or "").strip() or None
        if c is None:
            c = Course(org_id=org_id, code=code, subject=code.split()[0], title=title[:300], credits=nebula.credits(nc.get("credit_hours")), description=desc)
            db.add(c)
            existing[code] = c
            added += 1
        else:
            if desc and not c.description:
                c.description = desc
            if c.title in ("TBD", code) and title:
                c.title = title[:300]
            updated += 1
        db.flush()
        if not c.skills:
            map_course_skills(db, c, ids)
        if i % 250 == 0:
            set_progress(db, task, f"Imported {i} of {len(latest)} courses…")
            db.commit()
    db.commit()
    set_progress(db, task, "Linking prerequisites…")
    with_edges = set(db.scalars(select(CoursePrereq.course_id)))
    edges = 0
    for code, nc in latest.items():
        c = existing[code]
        if c.id in with_edges:
            continue  # keep curated JSOM prerequisites
        for gi, group in enumerate(nebula.prereq_groups(nc.get("prerequisites"), code_of)):
            for req_code in group:
                r = existing.get(req_code)
                if r and r.id != c.id:
                    db.add(CoursePrereq(course_id=c.id, requires_id=r.id, group=gi))
                    edges += 1
        db.flush()
    db.commit()
    return {"courses_in_nebula": len(latest), "added": added, "updated": updated, "prerequisite_links": edges}


@handler("gap.import_syllabus")
def import_syllabus(db: Session, task: Task) -> dict:
    """Download an official UTD syllabus, store it and run the gap analysis."""
    from ..models import Course, Syllabus
    from ..routers.gap import run_analysis
    from . import parser, syllabi
    from .tasks import set_progress

    p = task.payload
    set_progress(db, task, "Downloading the official syllabus…")
    filename, text = syllabi.download(p["url"])
    course = db.get(Course, p["course_id"])
    syl = Syllabus(org_id=task.org_id, owner_id=task.user_id, course_id=course.id, code=course.code, title=course.title,
                   semester=p.get("term"), filename=filename, raw_text=text, topics=parser.extract_topics(text))
    db.add(syl)
    db.commit()
    return {"syllabus_id": syl.id, **run_analysis(db, syl.id, p.get("target", "auto"), extract=True, task=task, user_id=task.user_id)}
