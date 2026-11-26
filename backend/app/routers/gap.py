"""CometGap API — syllabi, gap analyses, market demand, program heatmaps, exports."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..db import get_db
from ..models import Course, ForgeDraft, GapAnalysis, GapDecision, GapReview, Job, JobSample, Program, Syllabus, SyllabusSkill, SyllabusVersion, User
from ..security import audit, require_roles
from ..services import decisions as decsvc
from ..services import gap as gapsvc
from ..services import versions as vs
from ..services import parser, reports, tasks
from ..services import skills as sk

router = APIRouter(prefix="/api/gap", tags=["cometgap"])
faculty = require_roles("faculty")


def _own(db: Session, user: User, sid: str) -> Syllabus:
    s = db.get(Syllabus, sid)
    if not s or s.org_id != user.org_id or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Syllabus not found")
    return s


def _brief(s: Syllabus, latest: dict | None | bool = False) -> dict:
    """latest: the latest analysis as a dict (from _latest_analyses), None if there is none, or False to load it."""
    if latest is False:
        last = s.analyses[0] if s.analyses else None
        latest = {"id": last.id, "score": last.score, "target": last.target, "created_at": last.created_at} if last else None
    return {"id": s.id, "title": s.title, "code": s.code, "semester": s.semester, "filename": s.filename,
            "course_id": s.course_id, "skill_count": len(s.skills), "created_at": s.created_at,
            "pilot_approved": s.pilot_approved, "approved_by": s.approved_by, "approved_at": s.approved_at, "approval_note": s.approval_note,
            "latest": latest}


def _latest_briefs(db: Session, syllabus_ids: list[str]) -> dict[str, dict]:
    """Latest analysis per syllabus, columns only (the full result JSON is large and not needed for a list)."""
    if not syllabus_ids:
        return {}
    rows = db.execute(select(GapAnalysis.syllabus_id, GapAnalysis.id, GapAnalysis.score, GapAnalysis.target, GapAnalysis.created_at)
                      .where(GapAnalysis.syllabus_id.in_(syllabus_ids)).order_by(GapAnalysis.created_at.desc()))
    out: dict[str, dict] = {}
    for sid, aid, score, target, created in rows:
        out.setdefault(sid, {"id": aid, "score": score, "target": target, "created_at": created})
    return out


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
    syllabi = list(db.scalars(q.order_by(Syllabus.created_at.desc())))
    latest = _latest_briefs(db, [s.id for s in syllabi])
    return [_brief(s, latest.get(s.id)) for s in syllabi]


@router.post("/syllabi", status_code=201)
async def upload_syllabus(
    title: str = Form(...), code: str = Form(""), semester: str = Form(""), course_id: str = Form(""),
    target: str = Form("auto"), sample_id: str = Form(""), text: str = Form(""), file: UploadFile | None = File(None),
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
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": syl.id, "target": target, "extract": True, "sample_id": sample_id or None},
                      user.org_id, user.id)
    return {"id": syl.id, "task_id": t.id, "status": t.status, **(t.result or {})}


def run_analysis(db: Session, syllabus_id: str, target: str, top_n: int = 30, extract: bool = False, task=None,
                 sample_id: str | None = None, user_id: str | None = None, change_note: str | None = None,
                 proposal_id: str | None = None) -> dict:
    """Skill extraction (optional) + gap analysis. Runs inside a background task."""
    syl = db.get(Syllabus, syllabus_id)
    if extract:
        if task:
            tasks.set_progress(db, task, "Reading the syllabus and extracting skills…")
        found, engine = sk.extract(syl.raw_text, kind="course syllabus")
        syl.extraction_engine = engine
        ids = sk.skill_ids(db, found)
        syl.skills.clear()
        db.flush()
        for name, info in found.items():
            if name in ids:
                syl.skills.append(SyllabusSkill(skill_id=ids[name], mentions=info["mentions"], evidence=info.get("evidence"),
                                                excerpts=info.get("excerpts")))
        db.flush()
    if task:
        tasks.set_progress(db, task, "Comparing with current job postings…")
    ga = gapsvc.analyze(db, syl, target, top_n, sample_id=sample_id, user_id=user_id, change_note=change_note,
                        extraction_engine=getattr(syl, "extraction_engine", None) or "builtin")
    if proposal_id:
        from ..models import CurriculumProposal

        if (p := db.get(CurriculumProposal, proposal_id)) and p.syllabus_id == syl.id:
            p.adopted_version_id = ga.syllabus_version_id
    db.commit()
    return {"analysis_id": ga.id, "syllabus_id": syl.id, "score": ga.score}


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
    sample_id: str | None = None


@router.post("/syllabi/{sid}/analyze")
def reanalyze(sid: str, body: AnalyzeIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    if not body.sample_id and body.target not in ("auto", gapsvc.ALL, *ROLE_FAMILIES):
        raise HTTPException(400, "Unknown target")
    if body.sample_id:
        smp = db.get(JobSample, body.sample_id)
        if not smp or smp.org_id != user.org_id:
            raise HTTPException(404, "Job sample not found")
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": s.id, "target": body.target, "top_n": max(10, min(body.top_n, 60)),
                                          "sample_id": body.sample_id},
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
    reviews = {rv.skill_id: rv for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id))}
    return {"id": ga.id, "syllabus": {"id": s.id, "title": s.title, "code": s.code, "semester": s.semester,
                                      "pilot_approved": s.pilot_approved, "approved_by": s.approved_by},
            "score": ga.score, "target": ga.target, "job_count": ga.job_count, "engine": ga.engine,
            "sample_id": ga.sample_id if ga.sample_id and (smp := db.get(JobSample, ga.sample_id)) and smp.kind != "auto" else None,
            "inputs": vs.describe_inputs(db, ga),
            "decisions": {str(k): decsvc.out(v) for k, v in decsvc.active_for(db, s.id).items()},
            "decision_options": decsvc.DECISIONS,
            "created_at": ga.created_at, **ga.result,
            "reviews": {str(k): _review_out(v) for k, v in reviews.items()},
            "review_summary": gapsvc.review_summary(ga.result, reviews),
            "faculty_statuses": gapsvc.FACULTY_STATUSES}


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



# ── Faculty review of each skill ───────────────────────────────────────────────
def _review_out(rv: GapReview) -> dict:
    return {"skill_id": rv.skill_id, "system_status": rv.system_status, "faculty_status": rv.faculty_status, "decision": rv.decision,
            "rationale": rv.rationale, "action": rv.action, "action_note": rv.action_note,
            "reviewer": rv.reviewer.full_name if rv.reviewer else None, "carried_from": rv.carried_from, "updated_at": rv.updated_at}


class ReviewIn(BaseModel):
    faculty_status: str
    rationale: str | None = None
    action: str = "none"
    action_note: str | None = None


@router.put("/analyses/{aid}/reviews/{skill_id}")
def save_review(aid: str, skill_id: int, body: ReviewIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, ga = _analysis(db, user, aid)
    row = next((r for r in ga.result.get("skills", []) if r["skill_id"] == skill_id), None)
    if not row:
        raise HTTPException(404, "Skill is not part of this analysis")
    if body.faculty_status not in gapsvc.FACULTY_STATUSES:
        raise HTTPException(400, f"faculty_status must be one of {', '.join(gapsvc.FACULTY_STATUSES)}")
    if body.action not in ("none", "planned", "done"):
        raise HTTPException(400, "action must be none, planned or done")
    decision = gapsvc.decision_for(row["status"], body.faculty_status)
    rationale = (body.rationale or "").strip()
    if (decision == "corrected" or body.faculty_status == "not_relevant") and len(rationale) < 10:
        raise HTTPException(400, "Explain your classification (at least a short sentence) — it is the record of this correction")
    rv = db.scalar(select(GapReview).where(GapReview.analysis_id == ga.id, GapReview.skill_id == skill_id))
    if not rv:
        rv = GapReview(analysis_id=ga.id, skill_id=skill_id)
        db.add(rv)
    rv.reviewer_id, rv.system_status, rv.faculty_status, rv.decision = user.id, row["status"], body.faculty_status, decision
    rv.rationale, rv.action, rv.action_note, rv.carried_from = rationale or None, body.action, (body.action_note or "").strip() or None, None
    db.flush()
    from ..services import badges as badgesvc

    badgesvc.sync(db, user.org_id)  # a "practiced" confirmation can complete badges for students who finished the course
    audit(db, user, "gap.review", course=s.code or s.title, skill=row["name"], system=row["status"], faculty=body.faculty_status,
          decision=decision, follow_up=body.action)
    db.commit()
    db.refresh(rv)
    reviews = {r.skill_id: r for r in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id))}
    return {"review": _review_out(rv), "review_summary": gapsvc.review_summary(ga.result, reviews)}


@router.delete("/analyses/{aid}/reviews/{skill_id}")
def clear_review(aid: str, skill_id: int, user: User = Depends(faculty), db: Session = Depends(get_db)):
    _, ga = _analysis(db, user, aid)
    rv = db.scalar(select(GapReview).where(GapReview.analysis_id == ga.id, GapReview.skill_id == skill_id))
    if rv:
        db.delete(rv)
        db.commit()
    reviews = {r.skill_id: r for r in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id))}
    return {"review_summary": gapsvc.review_summary(ga.result, reviews)}


FINDING_COLS = ["course", "syllabus", "semester", "analysis_date", "job_sample", "sample_sources", "sample_dates", "skill", "category",
                "priority", "postings_requesting", "required", "preferred", "postings_in_sample", "skill_sources", "skill_dates",
                "mentions", "syllabus_excerpt", "system_signal", "faculty_classification", "decision", "rationale", "action",
                "action_note", "reviewer", "reviewed_at", "course_decision", "decision_rationale", "covered_in", "revisit_term",
                "decided_by", "decided_at", "decision_status", "forge_draft", "evidence_versions"]


def _finding_rows(db: Session, s: Syllabus, ga: GapAnalysis, gaps_only: bool = False) -> list[dict]:
    reviews = {rv.skill_id: rv for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id))}
    decs = decsvc.active_for(db, s.id)
    prov = ga.result.get("provenance") or {}
    sample = (prov.get("sample") or {}).get("name") or ga.target
    out = []
    for r in ga.result.get("skills", []):
        if gaps_only and r["status"] == "covered" and r["skill_id"] not in reviews:
            continue
        rv = reviews.get(r["skill_id"])
        out.append({"course": s.code or "", "syllabus": s.title, "semester": s.semester or "", "analysis_date": ga.created_at.date().isoformat(),
                    "job_sample": sample, "sample_sources": "; ".join(f"{k} {v}" for k, v in (prov.get("sources") or {}).items()),
                    "sample_dates": f"{prov.get('date_from') or '?'} to {prov.get('date_to') or '?'}",
                    "skill": r["name"], "category": r["category"], "priority": r["priority"], "postings_requesting": r["job_count"],
                    "required": r.get("required_count", ""), "preferred": r.get("preferred_count", ""), "postings_in_sample": ga.job_count,
                    "skill_sources": "; ".join(f"{k} {v}" for k, v in (r.get("sources") or {}).items()),
                    "skill_dates": f"{r.get('first_posted') or '?'} to {r.get('last_posted') or '?'}", "mentions": r["mentions"],
                    "syllabus_excerpt": " | ".join(r.get("excerpts") or []), "system_signal": r["status"],
                    "faculty_classification": rv.faculty_status if rv else "", "decision": rv.decision if rv else "not reviewed",
                    "rationale": rv.rationale or "" if rv else "", "action": rv.action if rv else "", "action_note": rv.action_note or "" if rv else "",
                    "reviewer": rv.reviewer.full_name if rv and rv.reviewer else "", "reviewed_at": rv.updated_at.isoformat() if rv else "",
                    **_decision_cols(decs.get(r["skill_id"]))})
    return out


def _decision_cols(d: GapDecision | None) -> dict:
    if not d:
        return {"course_decision": "", "decision_rationale": "", "covered_in": "", "revisit_term": "", "decided_by": "",
                "decided_at": "", "decision_status": "", "forge_draft": "", "evidence_versions": ""}
    e = d.evidence or {}
    return {"course_decision": decsvc.DECISIONS.get(d.decision, d.decision), "decision_rationale": d.rationale,
            "covered_in": "; ".join(d.covered_in or []), "revisit_term": d.revisit_term or "", "decided_by": d.reviewer_name or "",
            "decided_at": d.decided_at.isoformat(), "decision_status": d.status, "forge_draft": d.forge_draft_id or "",
            "evidence_versions": f"syllabus v{e.get('syllabus_version')} ({e.get('syllabus_hash')}); sample {e.get('sample_name')} ({e.get('sample_hash')}); "
                                 f"catalog {e.get('catalog_year')}; scoring {e.get('scoring_version')}"}


def _csv(rows: list[dict], name: str) -> Response:
    import csv
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FINDING_COLS)
    w.writeheader()
    w.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/analyses/{aid}/findings.csv")
def findings_csv(aid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, ga = _analysis(db, user, aid)
    return _csv(_finding_rows(db, s, ga), f"findings-{(s.code or s.title).replace(' ', '_')}.csv")


def _latest_analyses(db: Session, user: User, approved_only: bool) -> list[tuple[Syllabus, GapAnalysis]]:
    q = select(Syllabus).where(Syllabus.org_id == user.org_id)
    if approved_only:
        q = q.where(Syllabus.pilot_approved)
    elif user.role != "admin":
        q = q.where(Syllabus.owner_id == user.id)
    return [(s, s.analyses[0]) for s in db.scalars(q.order_by(Syllabus.code)) if s.analyses]


@router.get("/pilot/summary")
def pilot_summary(approved_only: bool = True, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Per approved syllabus: how many findings faculty confirmed, corrected or acted on."""
    rows, corrections = [], []
    totals = {"reviewed": 0, "confirmed": 0, "corrected": 0, "planned": 0, "done": 0, "gaps_total": 0, "gaps_reviewed": 0,
              "decisions": {k: 0 for k in decsvc.DECISIONS}, "implemented": 0}
    for s, ga in _latest_analyses(db, user, approved_only):
        reviews = {rv.skill_id: rv for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id))}
        summ = gapsvc.review_summary(ga.result, reviews)
        prov = ga.result.get("provenance") or {}
        decs = [d for d in decsvc.active_for(db, s.id).values()]
        summ["decisions"] = {k: sum(d.decision == k for d in decs) for k in decsvc.DECISIONS}
        summ["implemented"] = sum(d.status == "implemented" for d in decs)
        rows.append({"syllabus_id": s.id, "analysis_id": ga.id, "course": s.code, "title": s.title, "semester": s.semester,
                     "approved_by": s.approved_by, "pilot_approved": s.pilot_approved, "target": ga.target,
                     "sample": (prov.get("sample") or {}).get("name"), "job_count": ga.job_count,
                     "mention_score": ga.score, **summ})
        for k in ("reviewed", "confirmed", "corrected", "planned", "done", "gaps_total", "gaps_reviewed"):
            totals[k] += summ.get(k, 0)
        for k, v in summ["decisions"].items():
            totals.setdefault("decisions", {}).setdefault(k, 0)
            totals["decisions"][k] += v
        totals["implemented"] = totals.get("implemented", 0) + summ["implemented"]
        names = {r["skill_id"]: r["name"] for r in ga.result.get("skills", [])}
        corrections += [{"course": s.code, "skill": names.get(rv.skill_id), "system": rv.system_status, "faculty": rv.faculty_status,
                         "rationale": rv.rationale} for rv in reviews.values() if rv.decision == "corrected"]
    return {"syllabi": rows, "totals": totals, "corrections": corrections[:50], "approved_only": approved_only}


@router.get("/pilot/findings.csv")
def pilot_findings_csv(approved_only: bool = True, user: User = Depends(faculty), db: Session = Depends(get_db)):
    rows = [r for s, ga in _latest_analyses(db, user, approved_only) for r in _finding_rows(db, s, ga)]
    audit(db, user, "gap.pilot_export", rows=len(rows))
    db.commit()
    return _csv(rows, "cometiq-pilot-findings.csv")


# ── Documented job samples ─────────────────────────────────────────────────────
class SampleIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    method: str = Field(min_length=20, max_length=4000)
    role_family: str | None = None
    sources: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    location: str | None = None
    query: str | None = None
    max_postings: int = Field(500, ge=5, le=5000)


def _sample_out(db: Session, smp: JobSample, full: bool = False) -> dict:
    d = {"id": smp.id, "name": smp.name, "method": smp.method, "criteria": smp.criteria, "created_at": smp.created_at,
         "created_by": db.get(User, smp.created_by).full_name if smp.created_by and db.get(User, smp.created_by) else None,
         **gapsvc.sample_summary(db, smp.job_ids),
         "used_by": db.scalar(select(func.count()).select_from(GapAnalysis).where(GapAnalysis.sample_id == smp.id)) or 0}
    return d


@router.get("/samples")
def list_samples(user: User = Depends(faculty), db: Session = Depends(get_db)):
    q = select(JobSample).where(JobSample.org_id == user.org_id, JobSample.kind != "auto")
    return [_sample_out(db, s) for s in db.scalars(q.order_by(JobSample.created_at.desc()))]


@router.post("/samples", status_code=201)
def create_sample(body: SampleIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    from ..services.jobs import _parse_date

    q = select(Job.id).where(Job.is_open, (Job.org_id == user.org_id) | Job.org_id.is_(None))
    if body.role_family:
        q = q.where(Job.role_family == body.role_family)
    if body.sources:
        q = q.where(Job.source.in_(body.sources))
    if body.date_from and (d := _parse_date(body.date_from)):
        q = q.where(Job.posted_at >= d)
    if body.date_to and (d := _parse_date(body.date_to + "T23:59:59" if len(body.date_to) == 10 else body.date_to)):
        q = q.where(Job.posted_at <= d)
    if body.location:
        q = q.where(Job.location.ilike(f"%{body.location}%"))
    if body.query:
        q = q.where(Job.title.ilike(f"%{body.query}%"))
    ids = list(db.scalars(q.order_by(Job.posted_at.desc()).limit(body.max_postings)))
    if len(ids) < 5:
        raise HTTPException(400, f"Only {len(ids)} postings match — widen the criteria (a sample needs at least 5)")
    snap = vs.snapshot_jobs(db, ids)
    smp = JobSample(org_id=user.org_id, name=body.name.strip(), method=body.method.strip(), created_by=user.id, job_ids=ids,
                    snapshot=snap, content_hash=vs._hash(snap), kind="documented",
                    criteria={k: v for k, v in body.model_dump(exclude={"name", "method"}).items() if v not in (None, [], "")})
    db.add(smp)
    audit(db, user, "gap.sample.create", name=smp.name, postings=len(ids))
    db.commit()
    return _sample_out(db, smp)


@router.get("/samples/{sid}/postings.csv")
def sample_csv(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    import csv
    import io

    smp = db.get(JobSample, sid)
    if not smp or smp.org_id != user.org_id:
        raise HTTPException(404, "Sample not found")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"# Job sample: {smp.name}"])
    w.writerow([f"# Method: {smp.method}"])
    w.writerow([f"# Criteria: {smp.criteria}"])
    w.writerow([f"# Frozen {smp.created_at:%Y-%m-%d} with {len(smp.job_ids)} postings"])
    w.writerow(["title", "company", "location", "role_family", "source", "posted", "url", "required_skills", "preferred_skills"])
    for j in db.scalars(select(Job).where(Job.id.in_(smp.job_ids)).order_by(Job.posted_at.desc())):
        w.writerow([j.title, j.company, j.location, j.role_family, j.source, j.posted_at.date().isoformat() if j.posted_at else "", j.url,
                    "; ".join(s.skill.name for s in j.skills if s.importance == "required"),
                    "; ".join(s.skill.name for s in j.skills if s.importance != "required")])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="job-sample-{smp.name.replace(" ", "_")[:40]}.csv"'})


@router.delete("/samples/{sid}")
def delete_sample(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    smp = db.get(JobSample, sid)
    if not smp or smp.org_id != user.org_id or smp.kind == "auto" or (user.role != "admin" and smp.created_by != user.id):
        raise HTTPException(404, "Sample not found")
    if db.scalar(select(func.count()).select_from(GapAnalysis).where(GapAnalysis.sample_id == smp.id)):
        raise HTTPException(409, "This sample is the evidence for existing analyses and can't be deleted")
    db.delete(smp)
    db.commit()
    return {"ok": True}



class ApprovalIn(BaseModel):
    approved: bool
    approved_by: str | None = Field(None, max_length=200)   # e.g. "Dr. Lee, instructor of record"
    note: str | None = Field(None, max_length=2000)


@router.post("/syllabi/{sid}/approval")
def set_approval(sid: str, body: ApprovalIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Mark a syllabus as approved for use in the pilot (and by whom)."""
    from datetime import datetime, timezone

    s = _own(db, user, sid)
    if body.approved and len((body.approved_by or "").strip()) < 3:
        raise HTTPException(400, "Record who approved this syllabus for the pilot")
    s.pilot_approved = body.approved
    s.approved_by = (body.approved_by or "").strip() or None if body.approved else None
    s.approved_at = datetime.now(timezone.utc) if body.approved else None
    s.approval_note = body.note if body.approved else None
    audit(db, user, "gap.syllabus.approval", syllabus=s.title, approved=body.approved, by=s.approved_by)
    db.commit()
    return _brief(s)


# ── Versions, history and comparison ───────────────────────────────────────────
@router.post("/syllabi/{sid}/versions", status_code=202)
async def new_version(
    sid: str, semester: str = Form(...), change_note: str = Form(""), text: str = Form(""), target: str = Form(""),
    sample_id: str = Form(""), file: UploadFile | None = File(None), user: User = Depends(faculty), db: Session = Depends(get_db),
):
    """Upload the syllabus for a new semester. The previous version, and every report based on it, is kept."""
    syl = _own(db, user, sid)
    if file is not None and file.filename:
        filename, raw = await parser.read_upload(file)
    elif len(text.strip()) >= 40:
        filename, raw = None, text
    else:
        raise HTTPException(400, "Upload a PDF/DOCX/TXT file or paste at least a paragraph of syllabus text")
    if len(semester.strip()) < 4:
        raise HTTPException(400, "Which semester is this version for? e.g. Fall 2027")
    vs.ensure_version(db, syl, user_id=user.id)  # make sure the version being replaced is saved first
    syl.raw_text, syl.filename, syl.semester, syl.topics = raw, filename, semester.strip(), parser.extract_topics(raw)
    last = syl.analyses[0] if syl.analyses else None
    keep_sample = sample_id or (last.sample_id if last and last.sample_id and db.get(JobSample, last.sample_id).kind != "auto" else "")
    audit(db, user, "gap.syllabus.version", syllabus=syl.title, semester=syl.semester)
    db.commit()
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": syl.id, "target": target or (last.target if last and not keep_sample else "auto"),
                                          "extract": True, "sample_id": keep_sample or None, "change_note": change_note.strip() or None},
                      user.org_id, user.id)
    return {"id": syl.id, "task_id": t.id, "status": t.status, **(t.result or {})}


def _version_out(db: Session, v: SyllabusVersion) -> dict:
    by = db.get(User, v.created_by) if v.created_by else None
    return {"id": v.id, "version": v.version, "semester": v.semester, "filename": v.filename, "created_at": v.created_at,
            "change_note": v.change_note, "text_hash": v.text_hash[:12], "skill_count": len(v.skills or {}),
            "engine": v.extraction_engine, "taxonomy_version": v.taxonomy_version, "created_by": by.full_name if by else None}


@router.get("/syllabi/{sid}/history")
def history(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Versions of the syllabus, every report with its recorded inputs, and what changed between consecutive reports."""
    syl = _own(db, user, sid)
    versions = list(db.scalars(select(SyllabusVersion).where(SyllabusVersion.syllabus_id == syl.id).order_by(SyllabusVersion.version)))
    analyses = sorted(syl.analyses, key=lambda a: a.created_at)
    reports, steps, prev = [], [], None
    for ga in analyses:
        inp = vs.describe_inputs(db, ga)
        reports.append({"id": ga.id, "created_at": ga.created_at, "score": ga.score, "target": ga.target, "job_count": ga.job_count,
                        "inputs": inp})
        if inp["recorded"]:
            if prev is not None:
                c = vs.compare(db, prev, ga)
                steps.append({k: c[k] for k in ("from", "to", "total", "effects")} | {"skills_changed": len(c["skills"])})
            prev = ga
    return {"syllabus": _brief(syl), "versions": [_version_out(db, v) for v in versions], "reports": reports, "steps": steps,
            "scoring_version": vs.SCORING_VERSION, "taxonomy_version": vs.taxonomy_version()}


@router.get("/syllabi/{sid}/versions/{vid}/text")
def version_text(sid: str, vid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    syl = _own(db, user, sid)
    v = db.get(SyllabusVersion, vid)
    if not v or v.syllabus_id != syl.id:
        raise HTTPException(404, "Version not found")
    return {**_version_out(db, v), "text": v.raw_text, "skills": v.skills}


@router.get("/compare")
def compare_reports(a: str, b: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    sa, ga = _analysis(db, user, a)
    sb, gb = _analysis(db, user, b)
    if sa.id != sb.id and (not sa.code or sa.code != sb.code):
        raise HTTPException(400, "Compare reports of the same course")
    if ga.created_at > gb.created_at:
        ga, gb = gb, ga
    return vs.compare(db, ga, gb)


@router.get("/analyses/{aid}/reproduce")
def reproduce(aid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    _, ga = _analysis(db, user, aid)
    return vs.reproduce(db, ga)


# ── Faculty decisions ──────────────────────────────────────────────────────────
class DecisionIn(BaseModel):
    decision: str
    rationale: str = Field("", max_length=4000)
    covered_in: list[str] | None = None
    revisit_term: str | None = Field(None, max_length=40)


@router.put("/analyses/{aid}/decisions/{skill_id}")
def save_decision(aid: str, skill_id: int, body: DecisionIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, ga = _analysis(db, user, aid)
    d = decsvc.record(db, user, s, ga, skill_id, body.decision, body.rationale, body.covered_in, body.revisit_term)
    audit(db, user, "gap.decision", course=s.code or s.title, skill=d.skill.name if d.skill else skill_id, decision=d.decision)
    db.commit()
    db.refresh(d)
    return decsvc.out(d)


def _decision(db: Session, user: User, did: str) -> tuple[Syllabus, GapDecision]:
    d = db.get(GapDecision, did)
    if not d or d.org_id != user.org_id:
        raise HTTPException(404, "Decision not found")
    return _own(db, user, d.syllabus_id), d


@router.get("/syllabi/{sid}/decisions")
def list_decisions(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    syl = _own(db, user, sid)
    rows = list(db.scalars(select(GapDecision).where(GapDecision.syllabus_id == syl.id).order_by(GapDecision.decided_at.desc())))
    return {"active": [decsvc.out(d) for d in rows if d.status != "superseded"],
            "history": [decsvc.out(d) for d in rows if d.status == "superseded"], "options": decsvc.DECISIONS}


class DecisionStatusIn(BaseModel):
    status: str
    note: str | None = Field(None, max_length=2000)


@router.post("/decisions/{did}/status")
def decision_status(did: str, body: DecisionStatusIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, d = _decision(db, user, did)
    if d.status == "superseded":
        raise HTTPException(409, "This decision was replaced by a newer one")
    if body.status not in ("implemented", "open", "drafted"):
        raise HTTPException(400, "status must be implemented, drafted or open")
    if body.status == "implemented" and d.decision != "add_here":
        raise HTTPException(400, "Only 'add to this course' decisions are implemented in this syllabus")
    d.status = "drafted" if body.status == "open" and d.forge_draft_id else body.status
    d.implemented_note = ((body.note or "").strip() or None) if body.status == "implemented" else d.implemented_note
    audit(db, user, "gap.decision.status", course=s.code or s.title, skill=d.skill.name, status=d.status)
    db.commit()
    return decsvc.out(d)


class LinkIn(BaseModel):
    draft_id: str


@router.post("/decisions/{did}/link-draft")
def link_draft(did: str, body: LinkIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    s, d = _decision(db, user, did)
    dr = db.get(ForgeDraft, body.draft_id)
    if not dr or dr.org_id != user.org_id or dr.syllabus_id != s.id:
        raise HTTPException(404, "Draft not found for this course")
    if d.decision != "add_here":
        raise HTTPException(400, "Only 'add to this course' decisions link to a draft")
    d.forge_draft_id = dr.id
    if d.status == "open":
        d.status = "drafted"
    db.commit()
    return decsvc.out(d)


@router.post("/syllabi/{sid}/decisions/draft", status_code=202)
def draft_from_decisions(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Generate one CometForge draft that adds every accepted skill, and link the decisions to it."""
    syl = _own(db, user, sid)
    accepted = [d for d in decsvc.active_for(db, syl.id).values() if d.decision == "add_here" and d.status in ("open", "drafted")]
    if not accepted:
        raise HTTPException(400, "No accepted additions yet: choose 'Add to this course' on a reviewed gap first")
    aid = accepted[0].analysis_id or (syl.analyses[0].id if syl.analyses else None)
    t = tasks.enqueue(db, "forge.generate", {"user_id": user.id, "analysis_id": aid, "syllabus_id": syl.id,
                                             "focus_skills": [d.skill.name for d in accepted], "decision_ids": [d.id for d in accepted],
                                             "weeks": 15, "framework": "AACSB"}, user.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


@router.get("/syllabi/{sid}/proposed-changes")
def proposed(sid: str, draft_id: str | None = None, user: User = Depends(faculty), db: Session = Depends(get_db)):
    syl = _own(db, user, sid)
    accepted = [d for d in decsvc.active_for(db, syl.id).values() if d.decision == "add_here"]
    did = draft_id or next((d.forge_draft_id for d in accepted if d.forge_draft_id), None)
    draft = db.get(ForgeDraft, did) if did else None
    if draft and (draft.org_id != user.org_id or draft.syllabus_id != syl.id):
        raise HTTPException(404, "Draft not found for this course")
    drafts = [{"id": x.id, "version": x.version, "status": x.status, "created_at": x.created_at}
              for x in db.scalars(select(ForgeDraft).where(ForgeDraft.syllabus_id == syl.id).order_by(ForgeDraft.version.desc()))]
    return {**decsvc.proposed_changes(db, syl, draft, accepted), "drafts": drafts}


# ── Syllabus copilot ───────────────────────────────────────────────────────────
class CopilotIn(BaseModel):
    syllabus_id: str
    text: str = Field(max_length=200000)


@router.post("/copilot/preview")
def copilot_preview(body: CopilotIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    from ..services import copilot

    return copilot.preview(db, _own(db, user, body.syllabus_id), body.text)
