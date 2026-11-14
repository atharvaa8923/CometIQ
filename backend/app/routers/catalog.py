"""Shared knowledge graph: programs, courses, prerequisites, skills, meta."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..data.taxonomy import CATEGORIES, ROLE_FAMILIES
from ..db import get_db
from ..models import Course, CoursePrereq, Job, JobSkill, Program, Skill, User
from ..security import current_user
from ..services import ai

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/meta")
def meta(user: User = Depends(current_user)):
    return {"ai_enabled": ai.enabled(), "role_families": list(ROLE_FAMILIES), "categories": CATEGORIES}


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
            "prereq_notes": p.prereq_notes,
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
