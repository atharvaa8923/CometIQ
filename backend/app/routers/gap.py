"""CometGap API — syllabi, gap analyses, market demand, program heatmaps, exports."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..db import get_db
from ..models import Course, GapAnalysis, Job, Program, Syllabus, SyllabusSkill, User
from ..security import audit, require_roles
from ..services import gap as gapsvc
from ..services import parser, reports, tasks
from ..services import skills as sk

router = APIRouter(prefix="/api/gap", tags=["cometgap"])
faculty = require_roles("faculty")


def _own(db: Session, user: User, sid: str) -> Syllabus:
    s = db.get(Syllabus, sid)
    if not s or s.org_id != user.org_id or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Syllabus not found")
    return s


def _brief(s: Syllabus) -> dict:
    last = s.analyses[0] if s.analyses else None
    return {"id": s.id, "title": s.title, "code": s.code, "semester": s.semester, "filename": s.filename,
            "course_id": s.course_id, "skill_count": len(s.skills), "created_at": s.created_at,
            "latest": {"id": last.id, "score": last.score, "target": last.target, "created_at": last.created_at} if last else None}


@router.get("/targets")
def targets(user: User = Depends(faculty), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Job.role_family, func.count()).where(Job.is_open, (Job.org_id == user.org_id) | Job.org_id.is_(None))
                             .group_by(Job.role_family)).all())
    return [{"name": gapsvc.ALL, "job_count": sum(counts.values())}] + [
        {"name": f, "job_count": counts.get(f, 0)} for f in ROLE_FAMILIES]


@router.get("/market")
def market(target: str = gapsvc.ALL, user: User = Depends(faculty), db: Session = Depends(get_db)):
    demand, n = gapsvc.market_demand(db, target, user.org_id)
    return {"target": target, "job_count": n, "skills": demand[:60]}


@router.get("/syllabi")
def list_syllabi(user: User = Depends(faculty), db: Session = Depends(get_db)):
    q = select(Syllabus).where(Syllabus.org_id == user.org_id)
    if user.role != "admin":
        q = q.where(Syllabus.owner_id == user.id)
    return [_brief(s) for s in db.scalars(q.order_by(Syllabus.created_at.desc()))]


@router.post("/syllabi", status_code=201)
async def upload_syllabus(
    title: str = Form(...), code: str = Form(""), semester: str = Form(""), course_id: str = Form(""),
    target: str = Form("auto"), text: str = Form(""), file: UploadFile | None = File(None),
    user: User = Depends(faculty), db: Session = Depends(get_db),
):
    if file is not None and file.filename:
        filename, raw = await parser.read_upload(file)
    elif len(text.strip()) >= 40:
        filename, raw = None, text
    else:
        raise HTTPException(400, "Upload a PDF/DOCX/TXT file or paste at least a paragraph of syllabus text")
    course = db.get(Course, course_id) if course_id else None
    if course and course.org_id != user.org_id:
        course = None
    if not course and code:
        course = db.scalar(select(Course).where(Course.org_id == user.org_id, func.upper(Course.code) == code.strip().upper()))
    syl = Syllabus(org_id=user.org_id, owner_id=user.id, course_id=course.id if course else None,
                   code=(code or (course.code if course else "")).strip().upper() or None, title=title.strip(),
                   semester=semester.strip() or None, filename=filename, raw_text=raw, topics=parser.extract_topics(raw))
    db.add(syl)
    audit(db, user, "gap.syllabus.upload", syllabus=syl.title)
    db.commit()
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": syl.id, "target": target, "extract": True}, user.org_id, user.id)
    return {"id": syl.id, "task_id": t.id, "status": t.status, **(t.result or {})}


def run_analysis(db: Session, syllabus_id: str, target: str, top_n: int = 30, extract: bool = False, task=None) -> dict:
    """Skill extraction (optional) + gap analysis. Runs inside a background task."""
    syl = db.get(Syllabus, syllabus_id)
    if extract:
        if task:
            tasks.set_progress(db, task, "Reading the syllabus and extracting skills…")
        found, engine = sk.extract(syl.raw_text, kind="course syllabus")
        ids = sk.skill_ids(db, found)
        syl.skills.clear()
        db.flush()
        for name, info in found.items():
            if name in ids:
                syl.skills.append(SyllabusSkill(skill_id=ids[name], mentions=info["mentions"], evidence=info.get("evidence")))
        db.flush()
    if task:
        tasks.set_progress(db, task, "Comparing with current job postings…")
    ga = gapsvc.analyze(db, syl, target, top_n)
    db.commit()
    return {"analysis_id": ga.id, "score": ga.score}


@router.get("/syllabi/{sid}")
def get_syllabus(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    return {**_brief(s), "topics": s.topics, "text_preview": s.raw_text[:3000],
            "skills": [{"id": ss.skill.id, "name": ss.skill.name, "category": ss.skill.category, "mentions": ss.mentions,
                        "evidence": ss.evidence} for ss in sorted(s.skills, key=lambda x: -x.mentions)],
            "analyses": [{"id": a.id, "score": a.score, "target": a.target, "job_count": a.job_count, "engine": a.engine,
                          "created_at": a.created_at} for a in s.analyses]}


@router.delete("/syllabi/{sid}")
def delete_syllabus(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    db.delete(s)
    audit(db, user, "gap.syllabus.delete", syllabus=s.title)
    db.commit()
    return {"ok": True}


class AnalyzeIn(BaseModel):
    target: str = "auto"
    top_n: int = 30


@router.post("/syllabi/{sid}/analyze")
def reanalyze(sid: str, body: AnalyzeIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    if body.target not in ("auto", gapsvc.ALL, *ROLE_FAMILIES):
        raise HTTPException(400, "Unknown target")
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": s.id, "target": body.target, "top_n": max(10, min(body.top_n, 60))},
                      user.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **({"id": t.result["analysis_id"], "score": t.result["score"]} if t.result else {})}


def _analysis(db: Session, user: User, aid: str) -> tuple[Syllabus, GapAnalysis]:
    ga = db.get(GapAnalysis, aid)
    if not ga:
        raise HTTPException(404, "Analysis not found")
    return _own(db, user, ga.syllabus_id), ga


@router.get("/analyses/{aid}")
def get_analysis(aid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, ga = _analysis(db, user, aid)
    return {"id": ga.id, "syllabus": {"id": s.id, "title": s.title, "code": s.code, "semester": s.semester},
            "score": ga.score, "target": ga.target, "job_count": ga.job_count, "engine": ga.engine,
            "created_at": ga.created_at, **ga.result}


@router.get("/analyses/{aid}/export.{fmt}")
def export(aid: str, fmt: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, ga = _analysis(db, user, aid)
    name = f"CometGap-{(s.code or s.title).replace(' ', '_')}"
    if fmt == "pdf":
        return Response(reports.gap_pdf(s, ga), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    if fmt == "xlsx":
        return Response(reports.gap_xlsx(s, ga), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    raise HTTPException(400, "Format must be pdf or xlsx")


@router.get("/programs/{pid}")
def program_heatmap(pid: str, target: str = gapsvc.ALL, top_n: int = 20, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = db.get(Program, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    return gapsvc.program_heatmap(db, p, target, max(8, min(top_n, 40)))


# ── Official UTD syllabi (via Nebula) ─────────────────────────────────────────
@router.get("/utd-syllabi")
def utd_syllabi(course_id: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    from ..services import nebula

    c = db.get(Course, course_id)
    if not c or c.org_id != user.org_id:
        raise HTTPException(404, "Course not found")
    live = nebula.course_live(c.subject, c.code.split()[-1])
    if not live.get("available"):
        return {"course": c.code, "available": False, "reason": live.get("reason"), "syllabi": []}
    return {"course": c.code, "available": True, "syllabi": live.get("syllabi", [])}


class ImportIn(BaseModel):
    course_id: str
    url: str
    term: str | None = None
    target: str = "auto"


@router.post("/import-utd-syllabus", status_code=202)
def import_utd_syllabus(body: ImportIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    from ..services import syllabi

    c = db.get(Course, body.course_id)
    if not c or c.org_id != user.org_id:
        raise HTTPException(404, "Course not found")
    if not syllabi.allowed_url(body.url):
        raise HTTPException(400, "Only official UTD syllabus links (HTTPS on utdallas.edu) can be imported")
    t = tasks.enqueue(db, "gap.import_syllabus", body.model_dump(), user.org_id, user.id)
    audit(db, user, "gap.import_utd_syllabus", course=c.code)
    db.commit()
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


class ProgramImportIn(BaseModel):
    program_id: str
    target: str = "auto"


@router.post("/import-program-syllabi", status_code=202)
def import_program_syllabi(body: ProgramImportIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Queue the latest official syllabus of every core course in a program."""
    from ..services import nebula

    p = db.get(Program, body.program_id)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    if not nebula.enabled():
        raise HTTPException(400, "Nebula is not configured (NEBULA_API_KEY)")
    queued, missing = [], []
    for pc in p.core:
        c = pc.course
        links = nebula.course_live(c.subject, c.code.split()[-1]).get("syllabi") or []
        if not links:
            missing.append(c.code)
            continue
        t = tasks.enqueue(db, "gap.import_syllabus", {"course_id": c.id, "url": links[0]["url"], "term": links[0]["term"],
                                                      "target": body.target}, user.org_id, user.id)
        queued.append({"course": c.code, "task_id": t.id, "term": links[0]["term"]})
    audit(db, user, "gap.import_program_syllabi", program=p.name, queued=len(queued))
    db.commit()
    return {"queued": queued, "no_syllabus": missing}
