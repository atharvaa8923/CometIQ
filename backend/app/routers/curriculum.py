"""Curriculum proposals (pull-request style review), the AACSB curriculum map, and outcomes of implemented changes."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Course, CurriculumMapEntry, CurriculumProposal, GapDecision, JobSample, Program, ProposalComment, ProposalReview, Skill,
                      Syllabus, User)
from ..security import audit, require_roles
from ..services import badges as badgesvc
from ..services import curriculum_map as cmap
from ..services import gap as gapsvc
from ..services import parser, tasks
from ..services import proposals as psvc
from ..services.notify import notify

router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])
faculty = require_roles("faculty")


def _now():
    return datetime.now(timezone.utc)


def _syllabus(db: Session, user: User, sid: str) -> Syllabus:
    s = db.get(Syllabus, sid)
    if not s or s.org_id != user.org_id or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Syllabus not found")
    return s


def _proposal(db: Session, user: User, pid: str) -> CurriculumProposal:
    p = db.get(CurriculumProposal, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Proposal not found")
    return p


def _author_only(p: CurriculumProposal, user: User) -> None:
    if p.author_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the author can change this proposal")


# ── Proposals ──────────────────────────────────────────────────────────────────
@router.get("/proposals")
def list_proposals(status: str = "", user: User = Depends(faculty), db: Session = Depends(get_db)):
    q = select(CurriculumProposal).where(CurriculumProposal.org_id == user.org_id)
    if status == "open":
        q = q.where(CurriculumProposal.status.in_(("draft", "in_review", "changes_requested", "approved")))
    elif status:
        q = q.where(CurriculumProposal.status == status)
    rows = [psvc.out(db, p) for p in db.scalars(q.order_by(CurriculumProposal.number.desc()))]
    # drafts are private to their author until submitted
    return [r for r in rows if r["status"] != "draft" or r["author_id"] == user.id or user.role == "admin"]


class ProposalIn(BaseModel):
    syllabus_id: str
    title: str = Field(min_length=5, max_length=300)
    summary: str = Field("", max_length=8000)
    effective_term: str | None = Field(None, max_length=40)
    draft_id: str | None = None
    start_from: str = "current"   # current: current syllabus + marked additions · draft: the full CometForge draft


@router.post("/proposals", status_code=201)
def create_proposal(body: ProposalIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    syl = _syllabus(db, user, body.syllabus_id)
    p = psvc.create(db, user, syl, body.title, body.summary, body.effective_term, body.draft_id, body.start_from)
    audit(db, user, "curriculum.proposal.create", number=p.number, course=syl.code)
    db.commit()
    return psvc.out(db, p, True)


@router.get("/proposals/{pid}")
def get_proposal(pid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    if p.status == "draft" and p.author_id != user.id and user.role != "admin":
        raise HTTPException(404, "Proposal not found")
    return psvc.out(db, p, True) | {"can_edit": p.author_id == user.id or user.role == "admin", "can_review": p.author_id != user.id}


class ProposalEdit(BaseModel):
    title: str | None = Field(None, min_length=5, max_length=300)
    summary: str | None = Field(None, max_length=8000)
    effective_term: str | None = Field(None, max_length=40)
    proposed_text: str | None = Field(None, max_length=200000)


@router.put("/proposals/{pid}")
def edit_proposal(pid: str, body: ProposalEdit, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    _author_only(p, user)
    if p.status not in ("draft", "changes_requested"):
        raise HTTPException(409, "A proposal can be edited while it is a draft or after changes were requested")
    for k in ("title", "summary", "effective_term"):
        v = getattr(body, k)
        if v is not None:
            setattr(p, k, v.strip())
    if body.proposed_text is not None and body.proposed_text != p.proposed_text:
        if len(body.proposed_text.strip()) < 40:
            raise HTTPException(400, "The proposed syllabus text is too short")
        p.proposed_text = body.proposed_text
    db.commit()
    return psvc.out(db, p, True)


@router.post("/proposals/{pid}/submit")
def submit(pid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Send for review. Resubmitting after changes were requested starts a new revision: earlier votes no longer count."""
    p = _proposal(db, user, pid)
    _author_only(p, user)
    if p.status not in ("draft", "changes_requested"):
        raise HTTPException(409, f"Can't submit a proposal that is {p.status.replace('_', ' ')}")
    if not p.effective_term or not badgesvc.term_key(p.effective_term):
        raise HTTPException(400, "Set the effective term (e.g. Fall 2027) before submitting")
    if p.status == "changes_requested":
        p.revision += 1
    p.status, p.submitted_at = "in_review", _now()
    for u in db.scalars(select(User).where(User.org_id == user.org_id, User.role.in_(("faculty", "admin")), User.is_active, User.id != p.author_id)):
        notify(db, u, "curriculum.review", f"Review requested: proposal #{p.number}", f"{p.author_name} asks for review of “{p.title}”.",
               f"/curriculum/proposals/{p.id}")
    audit(db, user, "curriculum.proposal.submit", number=p.number, revision=p.revision)
    db.commit()
    return psvc.out(db, p, True)


class CommentIn(BaseModel):
    body: str = Field(min_length=2, max_length=4000)
    anchor: str | None = Field(None, pattern=r"^[LR]\d{1,6}$")


@router.post("/proposals/{pid}/comments", status_code=201)
def comment(pid: str, body: CommentIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    if p.status in ("adopted", "withdrawn"):
        raise HTTPException(409, "This proposal is closed")
    anchor_text = None
    if body.anchor:
        rows = psvc.out(db, p, True)["diff"]
        side, n = body.anchor[0], int(body.anchor[1:])
        row = next((r for r in rows if (r["l"] if side == "L" else r["r"]) == n), None)
        if not row:
            raise HTTPException(400, "That line is not in this proposal")
        anchor_text = row["left"] if side == "L" else row["right"]
    c = ProposalComment(proposal_id=p.id, author_id=user.id, author_name=user.full_name, anchor=body.anchor, anchor_text=anchor_text,
                        revision=p.revision, body=body.body.strip())
    db.add(c)
    if p.author_id and p.author_id != user.id and (author := db.get(User, p.author_id)):
        notify(db, author, "curriculum.comment", f"New comment on proposal #{p.number}", f"{user.full_name}: {c.body[:200]}",
               f"/curriculum/proposals/{p.id}")
    db.commit()
    db.refresh(p)
    return psvc.out(db, p, True)


@router.post("/proposals/{pid}/comments/{cid}/resolve")
def resolve(pid: str, cid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    c = db.get(ProposalComment, cid)
    if not c or c.proposal_id != p.id:
        raise HTTPException(404, "Comment not found")
    if user.id not in (c.author_id, p.author_id) and user.role != "admin":
        raise HTTPException(403, "Only the commenter or the author can resolve this")
    c.resolved = not c.resolved
    db.commit()
    return psvc.out(db, p, True)


class ReviewIn(BaseModel):
    vote: str
    body: str | None = Field(None, max_length=4000)


@router.post("/proposals/{pid}/reviews", status_code=201)
def review(pid: str, body: ReviewIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    if p.author_id == user.id:
        raise HTTPException(403, "Authors can't review their own proposal")
    if p.status not in ("in_review", "changes_requested", "approved"):
        raise HTTPException(409, "This proposal is not open for review")
    if body.vote not in ("approve", "request_changes"):
        raise HTTPException(400, "vote must be approve or request_changes")
    if body.vote == "request_changes" and len((body.body or "").strip()) < 10:
        raise HTTPException(400, "Say what needs to change")
    db.add(ProposalReview(proposal_id=p.id, reviewer_id=user.id, reviewer_name=user.full_name, vote=body.vote,
                          body=(body.body or "").strip() or None, revision=p.revision))
    db.flush()
    db.refresh(p)
    before = p.status
    psvc.update_status(p)
    if p.author_id and (author := db.get(User, p.author_id)) and p.status != before:
        msg = {"approved": "was approved", "changes_requested": "needs changes", "in_review": "is back in review"}[p.status]
        notify(db, author, "curriculum.status", f"Proposal #{p.number} {msg}", f"Latest review by {user.full_name}.", f"/curriculum/proposals/{p.id}")
    audit(db, user, "curriculum.proposal.review", number=p.number, vote=body.vote, revision=p.revision)
    db.commit()
    return psvc.out(db, p, True)


@router.post("/proposals/{pid}/withdraw")
def withdraw(pid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    _author_only(p, user)
    if p.status in ("adopted", "withdrawn"):
        raise HTTPException(409, "This proposal is already closed")
    p.status, p.decided_at = "withdrawn", _now()
    db.commit()
    return psvc.out(db, p, True)


class AdoptIn(BaseModel):
    semester: str | None = Field(None, max_length=40)


@router.post("/proposals/{pid}/adopt", status_code=202)
def adopt(pid: str, body: AdoptIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Make the approved text the course's next syllabus version and re-run the analysis on it."""
    p = _proposal(db, user, pid)
    _author_only(p, user)
    if p.status != "approved":
        raise HTTPException(409, "Only approved proposals can be adopted")
    syl = db.get(Syllabus, p.syllabus_id)
    from ..services import versions as vs

    vs.ensure_version(db, syl, user_id=user.id)
    last = syl.analyses[0] if syl.analyses else None
    sample = last.sample_id if last and last.sample_id and db.get(JobSample, last.sample_id).kind != "auto" else None
    syl.raw_text, syl.semester, syl.filename = p.proposed_text, (body.semester or p.effective_term), f"proposal-{p.number}.txt"
    syl.topics = parser.extract_topics(p.proposed_text)
    p.status = "adopted"
    for d in db.scalars(select(GapDecision).where(GapDecision.id.in_(p.decision_ids or []), GapDecision.decision == "add_here",
                                                  GapDecision.status.in_(("open", "drafted")))):
        d.status, d.implemented_note = "implemented", f"Adopted through curriculum proposal #{p.number} ({p.effective_term})"
    audit(db, user, "curriculum.proposal.adopt", number=p.number, course=syl.code)
    db.commit()
    t = tasks.enqueue(db, "gap.analyze", {"syllabus_id": syl.id, "target": last.target if last and not sample else "auto", "extract": True,
                                          "sample_id": sample, "change_note": f"Adopted curriculum proposal #{p.number}", "proposal_id": p.id},
                      user.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **(t.result or {}), "proposal": psvc.out(db, p)}


@router.get("/proposals/{pid}/change-request.{fmt}")
def change_request(pid: str, fmt: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    p = _proposal(db, user, pid)
    form = psvc.change_form(db, p)
    name = f"course-change-request-{(form['course']['code'] or 'course').replace(' ', '_')}-proposal-{p.number}"
    if fmt == "json":
        return form
    if fmt == "pdf":
        return Response(psvc.change_form_pdf(form), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    if fmt == "docx":
        return Response(psvc.change_form_docx(form), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}.docx"'})
    raise HTTPException(400, "Format must be json, pdf or docx")


# ── Curriculum map ─────────────────────────────────────────────────────────────
def _program(db: Session, user: User, pid: str) -> Program:
    p = db.get(Program, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    return p


@router.get("/programs/{pid}/map")
def program_map(pid: str, target: str = gapsvc.ALL, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return cmap.build(db, _program(db, user, pid), target)


@router.get("/programs/{pid}/map.xlsx")
def program_map_xlsx(pid: str, target: str = gapsvc.ALL, user: User = Depends(faculty), db: Session = Depends(get_db)):
    prog = _program(db, user, pid)
    return Response(cmap.to_xlsx(cmap.build(db, prog, target)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="curriculum-map-{prog.name[:40].replace(" ", "_")}.xlsx"'})


class MapEntryIn(BaseModel):
    level: str
    rationale: str | None = Field(None, max_length=2000)


@router.put("/programs/{pid}/map/{course_id}/{skill_id}")
def set_entry(pid: str, course_id: str, skill_id: int, body: MapEntryIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    prog = _program(db, user, pid)
    if body.level not in cmap.LEVELS:
        raise HTTPException(400, "level must be I, P, M or -")
    if course_id not in {c.id for c, _ in cmap.program_courses(prog)}:
        raise HTTPException(404, "Course is not part of this program")
    if not db.get(Skill, skill_id):
        raise HTTPException(404, "Skill not found")
    if body.level == "M" and len((body.rationale or "").strip()) < 10:
        raise HTTPException(400, "Mastery needs a rationale: which assessment shows it?")
    e = db.scalar(select(CurriculumMapEntry).where(CurriculumMapEntry.program_id == prog.id, CurriculumMapEntry.course_id == course_id,
                                                   CurriculumMapEntry.skill_id == skill_id))
    if not e:
        e = CurriculumMapEntry(org_id=user.org_id, program_id=prog.id, course_id=course_id, skill_id=skill_id)
        db.add(e)
    e.level, e.rationale, e.set_by_id, e.set_by_name = body.level, (body.rationale or "").strip() or None, user.id, user.full_name
    db.flush()
    issued = badgesvc.sync(db, user.org_id)
    audit(db, user, "curriculum.map.set", program=prog.name, course=db.get(Course, course_id).code, skill_id=skill_id, level=body.level)
    db.commit()
    return {"ok": True, "badges_issued": issued}


@router.delete("/programs/{pid}/map/{course_id}/{skill_id}")
def clear_entry(pid: str, course_id: str, skill_id: int, user: User = Depends(faculty), db: Session = Depends(get_db)):
    prog = _program(db, user, pid)
    e = db.scalar(select(CurriculumMapEntry).where(CurriculumMapEntry.program_id == prog.id, CurriculumMapEntry.course_id == course_id,
                                                   CurriculumMapEntry.skill_id == skill_id))
    if e:
        db.delete(e)
        db.commit()
    return {"ok": True}


# ── Outcomes ───────────────────────────────────────────────────────────────────
@router.get("/outcomes")
def all_outcomes(user: User = Depends(faculty), db: Session = Depends(get_db)):
    decs = db.scalars(select(GapDecision).where(GapDecision.org_id == user.org_id, GapDecision.decision == "add_here",
                                                GapDecision.status == "implemented").order_by(GapDecision.decided_at.desc()))
    return {"decisions": [badgesvc.outcomes(db, d) for d in decs], "supply": badgesvc.skill_supply(db, user.org_id),
            "min_group": badgesvc.get_settings().OUTCOME_MIN_COHORT}


@router.get("/decisions/{did}/outcomes")
def decision_outcomes(did: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    d = db.get(GapDecision, did)
    if not d or d.org_id != user.org_id:
        raise HTTPException(404, "Decision not found")
    return badgesvc.outcomes(db, d)
