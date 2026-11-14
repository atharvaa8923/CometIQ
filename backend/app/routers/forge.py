"""CometForge API — generate, edit, version, approve and export syllabus drafts."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.forge_library import ACCREDITATION, DEFAULT_PROGRAM_GOALS
from ..db import get_db
from ..models import CourseSkill, ForgeDraft, GapAnalysis, Syllabus, User
from ..security import audit, require_roles
from ..services import forge as forgesvc
from ..services import reports, tasks
from ..services import skills as sk

router = APIRouter(prefix="/api/forge", tags=["cometforge"])
faculty = require_roles("faculty")


def _syllabus(db: Session, user: User, sid: str) -> Syllabus:
    s = db.get(Syllabus, sid)
    if not s or s.org_id != user.org_id or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Syllabus not found")
    return s


def _draft(db: Session, user: User, did: str) -> ForgeDraft:
    d = db.get(ForgeDraft, did)
    if not d or d.org_id != user.org_id or (user.role != "admin" and d.owner_id != user.id):
        raise HTTPException(404, "Draft not found")
    return d


def _scores(db: Session, d: ForgeDraft) -> dict:
    ga = db.get(GapAnalysis, d.analysis_id) if d.analysis_id else None
    if not ga:
        return {"before": None, "after": None, "target": None}
    added = set(d.content.get("gaps_addressed", [])) | {s for m in d.content.get("modules", []) if m.get("is_new") for s in m.get("skills", [])}
    return {"before": ga.score, "after": forgesvc.projected_score(ga.result, added), "target": ga.target}


def _out(db: Session, d: ForgeDraft, full: bool = True) -> dict:
    o = {"id": d.id, "title": d.title, "version": d.version, "status": d.status, "engine": d.engine, "syllabus_id": d.syllabus_id,
         "analysis_id": d.analysis_id, "created_at": d.created_at, "scores": _scores(db, d),
         "new_modules": sum(1 for m in d.content.get("modules", []) if m.get("is_new"))}
    if full:
        o["content"] = d.content
        o["versions"] = [{"id": v.id, "version": v.version, "status": v.status, "created_at": v.created_at}
                         for v in db.scalars(select(ForgeDraft).where(ForgeDraft.syllabus_id == d.syllabus_id,
                                                                      ForgeDraft.org_id == d.org_id).order_by(ForgeDraft.version))] if d.syllabus_id else []
    return o


@router.get("/options")
def options(user: User = Depends(faculty)):
    return {"frameworks": list(ACCREDITATION) + ["None"], "program_goals": DEFAULT_PROGRAM_GOALS}


@router.get("/drafts")
def list_drafts(user: User = Depends(faculty), db: Session = Depends(get_db)):
    q = select(ForgeDraft).where(ForgeDraft.org_id == user.org_id)
    if user.role != "admin":
        q = q.where(ForgeDraft.owner_id == user.id)
    return [_out(db, d, False) for d in db.scalars(q.order_by(ForgeDraft.created_at.desc()))]


class GenerateIn(BaseModel):
    analysis_id: str | None = None
    syllabus_id: str | None = None
    focus_skills: list[str] | None = None
    weeks: int = Field(15, ge=8, le=18)
    framework: str = "AACSB"
    program_goals: list[str] | None = None


@router.post("/drafts", status_code=202)
def generate(body: GenerateIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    ga = db.get(GapAnalysis, body.analysis_id) if body.analysis_id else None
    sid = ga.syllabus_id if ga else body.syllabus_id
    if not sid:
        raise HTTPException(400, "Provide a gap analysis or syllabus")
    _syllabus(db, user, sid)  # permission check now; generation runs in the background
    t = tasks.enqueue(db, "forge.generate", {"user_id": user.id, **body.model_dump()}, user.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


def run_generate(db: Session, user: User, body: GenerateIn, task=None) -> dict:
    ga = db.get(GapAnalysis, body.analysis_id) if body.analysis_id else None
    syl = _syllabus(db, user, ga.syllabus_id if ga else body.syllabus_id)
    if task:
        tasks.set_progress(db, task, "Designing modules, outcomes and assessments…")
    if not ga and syl.analyses:
        ga = syl.analyses[0]
    result = ga.result if ga else None
    focus = body.focus_skills
    if focus is None:
        focus = [g["name"] for g in (result or {}).get("gaps", []) if g["priority"] in ("critical", "high")][:6]
    content, engine = forgesvc.generate(syl, result, focus, body.weeks, body.framework,
                                        [g for g in (body.program_goals or []) if g.strip()] or None)
    version = 1 + max([d.version for d in db.scalars(select(ForgeDraft).where(ForgeDraft.syllabus_id == syl.id))], default=0)
    d = ForgeDraft(org_id=user.org_id, owner_id=user.id, syllabus_id=syl.id, analysis_id=ga.id if ga else None, version=version,
                   title=f"{syl.code or ''} {syl.title}".strip(), content=content.model_dump(), engine=engine)
    db.add(d)
    audit(db, user, "forge.generate", syllabus=syl.title, version=version, engine=engine)
    db.commit()
    return {"draft_id": d.id}


@router.get("/drafts/{did}")
def get_draft(did: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return _out(db, _draft(db, user, did))


class SaveIn(BaseModel):
    content: dict


@router.put("/drafts/{did}")
def save(did: str, body: SaveIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    d = _draft(db, user, did)
    if d.status == "approved":
        raise HTTPException(409, "Approved drafts are locked. Generate a new version to make changes.")
    try:
        content = forgesvc.ForgeSyllabus.model_validate(body.content)
    except ValidationError as e:
        raise HTTPException(422, f"Invalid syllabus content: {e.errors()[0]['msg']}")
    total = sum(a.weight for a in content.assessments)
    if total != 100:
        raise HTTPException(422, f"Assessment weights must total 100% (currently {total}%)")
    for i, m in enumerate(content.modules, 1):
        m.week = i
    d.content = content.model_dump()
    db.commit()
    return _out(db, d)


@router.post("/drafts/{did}/approve")
def approve(did: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Approve a draft and feed its skills back into the shared knowledge graph."""
    d = _draft(db, user, did)
    d.status = "approved"
    syl = db.get(Syllabus, d.syllabus_id) if d.syllabus_id else None
    updated = 0
    if syl and syl.course_id:
        names = {s for m in d.content["modules"] for s in m.get("skills", [])}
        ids = sk.skill_ids(db, names)
        existing = {cs.skill_id: cs for cs in db.scalars(select(CourseSkill).where(CourseSkill.course_id == syl.course_id))}
        for name, sid in ids.items():
            if sid in existing:
                existing[sid].weight = max(existing[sid].weight, 1.0)
            else:
                db.add(CourseSkill(course_id=syl.course_id, skill_id=sid, weight=1.0, source="forge"))
                updated += 1
    audit(db, user, "forge.approve", draft=d.title, version=d.version, skills_added=updated)
    db.commit()
    return {**_out(db, d), "graph_skills_added": updated}


@router.delete("/drafts/{did}")
def delete(did: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    d = _draft(db, user, did)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/drafts/{did}/export.{fmt}")
def export(did: str, fmt: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    d = _draft(db, user, did)
    name = f"{d.title.replace(' ', '_')}_v{d.version}"
    if fmt == "docx":
        return Response(reports.forge_docx(d), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}.docx"'})
    if fmt == "pdf":
        return Response(reports.forge_pdf(d), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    raise HTTPException(400, "Format must be docx or pdf")
