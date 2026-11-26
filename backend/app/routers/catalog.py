"""Shared knowledge graph: programs, courses, prerequisites, skills, meta."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..data.taxonomy import CATEGORIES, ROLE_FAMILIES
from ..db import get_db
from ..models import Course, CoursePrereq, Job, JobSkill, Program, Skill, User
from ..security import current_user, require_roles
from ..services import ai, nebula

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/meta")
def meta(user: User = Depends(current_user)):
    return {"ai_enabled": ai.enabled(), "nebula_enabled": nebula.enabled(), "role_families": list(ROLE_FAMILIES), "categories": CATEGORIES}


@router.get("/skills")
def skills(user: User = Depends(current_user), db: Session = Depends(get_db)):
    demand = dict(db.execute(select(JobSkill.skill_id, func.count()).join(Job).where(Job.is_open)
                             .group_by(JobSkill.skill_id)).all())
    return [{"id": s.id, "name": s.name, "category": s.category, "is_emerging": s.is_emerging,
             "job_count": demand.get(s.id, 0)} for s in db.scalars(select(Skill).order_by(Skill.category, Skill.name))]


def course_brief(c: Course) -> dict:
    return {"id": c.id, "code": c.code, "title": c.title, "credits": c.credits}


@router.get("/programs")
def programs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Program).where(Program.org_id == user.org_id).order_by(Program.type, Program.name))
    return [{"id": p.id, "name": p.name, "type": p.type, "department": p.department, "total_sch": p.total_sch,
             "is_stem": p.is_stem, "core_count": len(p.core), "concentrations": [{"id": c.id, "name": c.name} for c in p.concentrations]}
            for p in rows]


@router.get("/programs/{pid}")
def program(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Program, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    return {"id": p.id, "name": p.name, "type": p.type, "department": p.department, "total_sch": p.total_sch,
            "core_sch": p.core_sch, "elective_sch": p.elective_sch, "is_stem": p.is_stem, "catalog_url": p.catalog_url,
            "prereq_notes": p.prereq_notes, "catalog_year": p.catalog_year, "catalog_confirmed_by": p.catalog_confirmed_by,
            "catalog_confirmed_at": p.catalog_confirmed_at, "catalog_note": p.catalog_note,
            "core": [{**course_brief(pc.course), "or_group": pc.or_group} for pc in p.core],
            "concentrations": [{"id": c.id, "name": c.name, "required_sch": c.required_sch, "notes": c.notes,
                                "courses": [course_brief(cc.course) for cc in c.courses]} for c in p.concentrations]}


@router.get("/courses")
def courses(q: str = "", subject: str = "", limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Course).where(Course.org_id == user.org_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Course.code.ilike(like), Course.title.ilike(like)))
    if subject:
        stmt = stmt.where(Course.subject == subject.upper())
    return [course_brief(c) | {"subject": c.subject} for c in db.scalars(stmt.order_by(Course.code).limit(min(limit, 500)))]


@router.get("/courses/{cid}")
def course(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Course, cid)
    if not c or c.org_id != user.org_id:
        raise HTTPException(404, "Course not found")
    pre = db.execute(select(CoursePrereq, Course).join(Course, Course.id == CoursePrereq.requires_id)
                     .where(CoursePrereq.course_id == c.id)).all()
    unlocks = db.scalars(select(Course).join(CoursePrereq, CoursePrereq.course_id == Course.id)
                         .where(CoursePrereq.requires_id == c.id)).all()
    return {**course_brief(c), "description": c.description,
            "prerequisites": [{**course_brief(rc), "group": e.group} for e, rc in pre],
            "unlocks": [course_brief(u) for u in unlocks],
            "skills": [{"id": cs.skill.id, "name": cs.skill.name, "category": cs.skill.category, "weight": cs.weight,
                        "source": cs.source} for cs in c.skills]}


@router.get("/courses/{cid}/live")
def course_live(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Live sections, professors and grade distributions from UTD Nebula (cached 6 h)."""
    c = db.get(Course, cid)
    if not c or c.org_id != user.org_id:
        raise HTTPException(404, "Course not found")
    return {"course": c.code, **nebula.course_live(c.subject, c.code.split()[-1])}


class CatalogConfirmIn(BaseModel):
    catalog_year: str = Field(pattern=r"^20\d\d-\d\d$")
    confirmed_by: str = Field(min_length=3, max_length=200)   # program owner's name/role
    note: str | None = Field(None, max_length=2000)


@router.put("/programs/{pid}/catalog-confirmation")
def confirm_catalog(pid: str, body: CatalogConfirmIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Record that the program owner confirmed which catalog year the requirements follow."""
    from datetime import datetime, timezone

    from ..security import audit

    p = db.get(Program, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    p.catalog_year, p.catalog_confirmed_by, p.catalog_note = body.catalog_year, body.confirmed_by.strip(), body.note
    p.catalog_confirmed_at = datetime.now(timezone.utc)
    audit(db, user, "program.catalog_confirmed", program=p.name, year=body.catalog_year, by=body.confirmed_by)
    db.commit()
    return {"catalog_year": p.catalog_year, "catalog_confirmed_by": p.catalog_confirmed_by, "catalog_confirmed_at": p.catalog_confirmed_at}
