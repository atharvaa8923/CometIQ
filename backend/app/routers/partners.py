"""Skill stacks (role-ready credentials) and employer-sponsored projects for gaps faculty decided to add."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Course, ForgeDraft, GapAnalysis, GapDecision, Skill, SkillBadge, SkillStack, SponsoredProject, StackCompletion,
                      StackSubscription, StudentCourse, StudentProfile, Syllabus, User)
from ..security import audit, current_user, require_roles
from ..services import stacks as stacksvc
from ..services.badges import faculty_basis
from ..services.notify import notify

router = APIRouter(prefix="/api", tags=["partners"])
faculty = require_roles("faculty")
employer = require_roles("employer")


def _now():
    return datetime.now(timezone.utc)


# ── Skill stacks ───────────────────────────────────────────────────────────────
def _stack_out(db: Session, st: SkillStack) -> dict:
    names = {s.id: s.name for s in db.scalars(select(Skill).where(Skill.id.in_([r["skill_id"] for r in st.requirements])))}
    return {"id": st.id, "name": st.name, "role_family": st.role_family, "description": st.description, "is_active": st.is_active,
            "requirements": [{**r, "skill": names.get(r["skill_id"], "?")} for r in st.requirements],
            "completions": db.scalar(select(func.count()).select_from(StackCompletion).where(StackCompletion.stack_id == st.id)) or 0}


@router.get("/stacks")
def list_stacks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stacksvc.ensure_defaults(db, user.org_id)
    db.commit()
    rows = [s for s in db.scalars(select(SkillStack).where(SkillStack.org_id == user.org_id).order_by(SkillStack.name))
            if s.is_active or user.role in ("faculty", "admin")]
    out = [_stack_out(db, s) for s in rows]
    if user.role == "student":
        basis = faculty_basis(db, user.org_id)
        held = stacksvc._held(db, user.id)
        out = [o | {"progress": stacksvc.progress(db, s, user.id, basis, held)} for o, s in zip(out, rows)]
    if user.role == "employer":
        subs = set(db.scalars(select(StackSubscription.stack_id).where(StackSubscription.employer_id == user.id)))
        out = [o | {"subscribed": o["id"] in subs} for o in out]
    return out


class StackIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    role_family: str | None = Field(None, max_length=80)
    description: str = Field("", max_length=2000)
    requirements: list[dict] = Field(min_length=1, max_length=12)
    is_active: bool = True


def _validate_reqs(db: Session, reqs: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in reqs:
        sid, lvl = r.get("skill_id"), r.get("level", "practiced")
        if not isinstance(sid, int) or not db.get(Skill, sid) or lvl not in stacksvc.RANK or sid in seen:
            raise HTTPException(400, "Each requirement needs a distinct skill and a level (practiced or mastered)")
        seen.add(sid)
        out.append({"skill_id": sid, "level": lvl})
    return out


@router.post("/stacks", status_code=201)
def create_stack(body: StackIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    st = SkillStack(org_id=user.org_id, name=body.name.strip(), role_family=body.role_family, description=body.description.strip(),
                    requirements=_validate_reqs(db, body.requirements), is_active=body.is_active, created_by=user.id)
    db.add(st)
    db.flush()
    stacksvc.check_completions(db, user.org_id)
    audit(db, user, "stack.create", name=st.name)
    db.commit()
    return _stack_out(db, st)


@router.put("/stacks/{sid}")
def update_stack(sid: str, body: StackIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    st = db.get(SkillStack, sid)
    if not st or st.org_id != user.org_id:
        raise HTTPException(404, "Stack not found")
    st.name, st.role_family, st.description = body.name.strip(), body.role_family, body.description.strip()
    st.requirements, st.is_active = _validate_reqs(db, body.requirements), body.is_active
    db.flush()
    stacksvc.check_completions(db, user.org_id)
    db.commit()
    return _stack_out(db, st)


class SubscribeIn(BaseModel):
    subscribe: bool


@router.post("/stacks/{sid}/subscribe")
def subscribe(sid: str, body: SubscribeIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    st = db.get(SkillStack, sid)
    if not st or st.org_id != user.org_id:
        raise HTTPException(404, "Stack not found")
    sub = db.scalar(select(StackSubscription).where(StackSubscription.stack_id == sid, StackSubscription.employer_id == user.id))
    if body.subscribe and not sub:
        db.add(StackSubscription(stack_id=sid, employer_id=user.id))
    elif not body.subscribe and sub:
        db.delete(sub)
    db.commit()
    return {"subscribed": body.subscribe}


@router.get("/stacks/{sid}/completions")
def completions(sid: str, user: User = Depends(require_roles("employer", "faculty")), db: Session = Depends(get_db)):
    st = db.get(SkillStack, sid)
    if not st or st.org_id != user.org_id:
        raise HTTPException(404, "Stack not found")
    out = []
    for c in db.scalars(select(StackCompletion).where(StackCompletion.stack_id == sid).order_by(StackCompletion.completed_at.desc())):
        u, prof = db.get(User, c.student_id), db.get(StudentProfile, c.student_id)
        if not u or (user.role == "employer" and not (prof and prof.open_to_match)):
            continue
        out.append({"student_id": u.id, "name": u.full_name, "headline": prof.headline if prof else None, "completed_at": c.completed_at})
    return out


# ── Employer-sponsored projects ────────────────────────────────────────────────
def _own_syllabus(db: Session, user: User, sid: str) -> Syllabus:
    s = db.get(Syllabus, sid)
    if not s or s.org_id != user.org_id or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Course not found")
    return s


class ShareIn(BaseModel):
    share: bool
    note: str | None = Field(None, max_length=2000)


@router.put("/gap/decisions/{did}/share")
def share_decision(did: str, body: ShareIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Let employer partners see an accepted addition (course, skill and a note you write for them — not your internal rationale)."""
    d = db.get(GapDecision, did)
    if not d or d.org_id != user.org_id:
        raise HTTPException(404, "Decision not found")
    _own_syllabus(db, user, d.syllabus_id)
    if body.share and (d.decision != "add_here" or d.status == "superseded"):
        raise HTTPException(400, "Only current 'add to this course' decisions can be shared with partners")
    if body.share and len((body.note or "").strip()) < 10:
        raise HTTPException(400, "Write a short note for partners: what students should be able to do")
    d.share_with_partners, d.partner_note = body.share, (body.note or "").strip() or None
    audit(db, user, "partners.share", decision=d.id, share=body.share)
    db.commit()
    return {"id": d.id, "share_with_partners": d.share_with_partners, "partner_note": d.partner_note}


def _project_out(db: Session, p: SponsoredProject) -> dict:
    syl = db.get(Syllabus, p.syllabus_id)
    return {"id": p.id, "decision_id": p.decision_id, "syllabus_id": p.syllabus_id, "course_code": syl.code if syl else None,
            "course_title": syl.title if syl else None, "skill": p.skill.name if p.skill else None, "company": p.company, "kind": p.kind,
            "title": p.title, "description": p.description, "dataset_url": p.dataset_url, "deliverables": p.deliverables, "term": p.term,
            "status": p.status, "faculty_note": p.faculty_note, "decided_by": p.decided_by_name, "forge_draft_id": p.forge_draft_id,
            "participants": p.participants, "created_at": p.created_at, "decided_at": p.decided_at, "completed_at": p.completed_at}


@router.get("/partners/needs")
def needs(user: User = Depends(employer), db: Session = Depends(get_db)):
    """Curriculum needs faculty chose to share with employer partners."""
    mine = {p.decision_id for p in db.scalars(select(SponsoredProject).where(SponsoredProject.employer_id == user.id))}
    out = []
    for d in db.scalars(select(GapDecision).where(GapDecision.org_id == user.org_id, GapDecision.share_with_partners,
                                                  GapDecision.status.in_(("open", "drafted"))).order_by(GapDecision.decided_at.desc())):
        syl = db.get(Syllabus, d.syllabus_id)
        out.append({"decision_id": d.id, "course_code": syl.code, "course_title": syl.title, "skill": d.skill.name,
                    "note": d.partner_note, "shared_since": d.decided_at, "postings_requesting": (d.evidence or {}).get("postings_requesting"),
                    "postings_in_sample": (d.evidence or {}).get("postings_in_sample"), "already_offered": d.id in mine})
    return out


class ProjectIn(BaseModel):
    decision_id: str
    kind: str = Field("project", pattern="^(project|dataset|guest_session)$")
    title: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=30, max_length=6000)
    dataset_url: str | None = Field(None, max_length=1000)
    deliverables: list[str] = Field(default_factory=list, max_length=10)
    term: str | None = Field(None, max_length=40)


@router.post("/partners/projects", status_code=201)
def offer(body: ProjectIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    d = db.get(GapDecision, body.decision_id)
    if not d or d.org_id != user.org_id or not d.share_with_partners or d.status not in ("open", "drafted"):
        raise HTTPException(404, "This curriculum need is not open for partners")
    if body.dataset_url and not body.dataset_url.startswith("https://"):
        raise HTTPException(400, "Dataset links must start with https://")
    p = SponsoredProject(org_id=user.org_id, decision_id=d.id, syllabus_id=d.syllabus_id, skill_id=d.skill_id, employer_id=user.id,
                         company=user.company or user.full_name, kind=body.kind, title=body.title.strip(), description=body.description.strip(),
                         dataset_url=body.dataset_url, deliverables=[x.strip() for x in body.deliverables if x.strip()], term=body.term)
    db.add(p)
    syl = db.get(Syllabus, d.syllabus_id)
    owner = db.get(User, syl.owner_id)
    if owner:
        notify(db, owner, "partners.offer", f"{p.company} offered a {p.kind.replace('_', ' ')} for {syl.code}",
               f"“{p.title}” for {d.skill.name}. Review it in Course history → Partner offers.", f"/gap/course/{syl.id}?tab=partners")
    audit(db, user, "partners.offer", course=syl.code, skill=d.skill.name)
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


@router.get("/partners/projects")
def list_projects(syllabus_id: str = "", user: User = Depends(require_roles("employer", "faculty")), db: Session = Depends(get_db)):
    q = select(SponsoredProject).where(SponsoredProject.org_id == user.org_id)
    if user.role == "employer":
        q = q.where(SponsoredProject.employer_id == user.id)
    elif syllabus_id:
        _own_syllabus(db, user, syllabus_id)
        q = q.where(SponsoredProject.syllabus_id == syllabus_id)
    elif user.role != "admin":
        q = q.where(SponsoredProject.syllabus_id.in_(select(Syllabus.id).where(Syllabus.owner_id == user.id)))
    return [_project_out(db, p) for p in db.scalars(q.order_by(SponsoredProject.created_at.desc()))]


def _project_for_faculty(db: Session, user: User, pid: str) -> tuple[SponsoredProject, Syllabus]:
    p = db.get(SponsoredProject, pid)
    if not p or p.org_id != user.org_id:
        raise HTTPException(404, "Project not found")
    return p, _own_syllabus(db, user, p.syllabus_id)


class DecideIn(BaseModel):
    accept: bool
    note: str | None = Field(None, max_length=2000)


@router.post("/partners/projects/{pid}/decide")
def decide(pid: str, body: DecideIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Accepting creates a new CometForge draft version whose team project is the sponsor's project."""
    from ..services import forge as forgesvc

    p, syl = _project_for_faculty(db, user, pid)
    if p.status != "offered":
        raise HTTPException(409, f"This offer is already {p.status}")
    if not body.accept and len((body.note or "").strip()) < 5:
        raise HTTPException(400, "Tell the partner why (a short note)")
    p.status, p.faculty_note, p.decided_by_name, p.decided_at = ("accepted" if body.accept else "declined"), (body.note or "").strip() or None, user.full_name, _now()
    if body.accept:
        base = db.scalar(select(ForgeDraft).where(ForgeDraft.syllabus_id == syl.id).order_by(ForgeDraft.version.desc()).limit(1))
        if base:
            content = dict(base.content)
        else:
            ga = db.scalar(select(GapAnalysis).where(GapAnalysis.syllabus_id == syl.id).order_by(GapAnalysis.created_at.desc()).limit(1))
            content = forgesvc.build_builtin(syl, ga.result if ga else None, [p.skill.name], 15, "AACSB", []).model_dump()
        content["project"] = {"title": f"{p.title} (sponsored by {p.company})", "description": p.description
                              + (f" Dataset: {p.dataset_url}" if p.dataset_url else ""),
                              "deliverables": p.deliverables or ["Analysis notebook", "Recommendation memo", "Presentation to the partner"],
                              "skills": sorted(set((content.get("project") or {}).get("skills", [])) | {p.skill.name})}
        content["gaps_addressed"] = sorted(set(content.get("gaps_addressed") or []) | {p.skill.name})
        content["change_log"] = list(content.get("change_log") or []) + [f"Team project sponsored by {p.company}: {p.title} ({p.skill.name})."]
        version = 1 + max([d.version for d in db.scalars(select(ForgeDraft).where(ForgeDraft.syllabus_id == syl.id))], default=0)
        draft = ForgeDraft(org_id=syl.org_id, owner_id=user.id, syllabus_id=syl.id, analysis_id=base.analysis_id if base else None, version=version,
                           title=f"{syl.code or ''} {syl.title}".strip(), content=content, engine="builtin")
        db.add(draft)
        db.flush()
        p.forge_draft_id = draft.id
        d = db.get(GapDecision, p.decision_id) if p.decision_id else None
        if d and d.status == "open":
            d.forge_draft_id, d.status = draft.id, "drafted"
    if p.employer_id and (emp := db.get(User, p.employer_id)):
        notify(db, emp, "partners.decided", f"{syl.code}: your offer was {p.status}", p.faculty_note or f"{user.full_name} {p.status} “{p.title}”.", "/match")
    audit(db, user, "partners.decide", project=p.id, status=p.status)
    db.commit()
    return _project_out(db, p)


@router.get("/partners/projects/{pid}/candidates")
def candidates(pid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """Students enrolled in or completing the course, for recording who completed the sponsored project."""
    p, syl = _project_for_faculty(db, user, pid)
    cid = syl.course_id or db.scalar(select(Course.id).where(Course.org_id == syl.org_id, func.upper(Course.code) == (syl.code or "").upper()))
    rows = db.scalars(select(StudentCourse).where(StudentCourse.course_id == cid, StudentCourse.status.in_(("enrolled", "completed")))) if cid else []
    return [{"student_id": r.user_id, "name": db.get(User, r.user_id).full_name, "status": r.status, "term": r.term} for r in rows]


class CompleteIn(BaseModel):
    student_ids: list[str] = Field(min_length=1, max_length=500)
    term: str | None = Field(None, max_length=40)


@router.post("/partners/projects/{pid}/complete")
def complete(pid: str, body: CompleteIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    """The instructor records which students completed the sponsored project; each earns a badge naming the partner."""
    import secrets

    p, syl = _project_for_faculty(db, user, pid)
    if p.status not in ("accepted", "completed"):
        raise HTTPException(409, "Accept the offer first")
    cid = syl.course_id or db.scalar(select(Course.id).where(Course.org_id == syl.org_id, func.upper(Course.code) == (syl.code or "").upper()))
    if not cid:
        raise HTTPException(400, "Link this syllabus to a catalog course first")
    allowed = {c["student_id"] for c in candidates(pid, user, db)}
    unknown = [s for s in body.student_ids if s not in allowed]
    if unknown:
        raise HTTPException(400, "Some students are not enrolled in or completing this course")
    issued = 0
    for sid in set(body.student_ids):
        b = db.scalar(select(SkillBadge).where(SkillBadge.student_id == sid, SkillBadge.skill_id == p.skill_id, SkillBadge.course_id == cid))
        if b:
            b.partner, b.project_id = p.company, p.id
        else:
            db.add(SkillBadge(org_id=p.org_id, student_id=sid, skill_id=p.skill_id, course_id=cid, course_code=syl.code or "", level="practiced",
                              term=body.term or p.term, partner=p.company, project_id=p.id, public_token=secrets.token_urlsafe(18),
                              basis={"faculty": {"source": "sponsored project", "confirmed_by": user.full_name, "confirmed_at": _now().isoformat(),
                                                 "project": p.title, "partner": p.company},
                                     "completion": {"verified_by": user.full_name, "verified_at": _now().isoformat(), "term": body.term or p.term}}))
            issued += 1
        if stu := db.get(User, sid):
            notify(db, stu, "partners.badge", f"Badge earned: {p.skill.name} with {p.company}",
                   f"You completed “{p.title}” in {syl.code}. {p.company} gets first look at project participants.", "/match")
    p.status, p.completed_at = "completed", _now()
    db.flush()
    p.participants = db.scalar(select(func.count()).select_from(SkillBadge).where(SkillBadge.project_id == p.id)) or 0
    stacksvc.check_completions(db, p.org_id, set(body.student_ids))
    if p.employer_id and (emp := db.get(User, p.employer_id)):
        notify(db, emp, "partners.completed", f"{len(set(body.student_ids))} students completed your project",
               f"“{p.title}” in {syl.code}. See them under Partner projects.", "/match")
    audit(db, user, "partners.complete", project=p.id, students=len(set(body.student_ids)))
    db.commit()
    return _project_out(db, p) | {"badges_issued": issued}


@router.post("/partners/projects/{pid}/withdraw")
def withdraw(pid: str, user: User = Depends(employer), db: Session = Depends(get_db)):
    p = db.get(SponsoredProject, pid)
    if not p or p.employer_id != user.id:
        raise HTTPException(404, "Project not found")
    if p.status != "offered":
        raise HTTPException(409, "Only pending offers can be withdrawn")
    p.status = "withdrawn"
    db.commit()
    return _project_out(db, p)


@router.get("/partners/participants")
def participants(user: User = Depends(employer), db: Session = Depends(get_db)):
    """First look: students who completed this employer's sponsored projects (only those open to matching)."""
    pids = {p.id: p for p in db.scalars(select(SponsoredProject).where(SponsoredProject.employer_id == user.id))}
    out = []
    for b in db.scalars(select(SkillBadge).where(SkillBadge.project_id.in_(list(pids)), SkillBadge.status == "active")) if pids else []:
        u, prof = db.get(User, b.student_id), db.get(StudentProfile, b.student_id)
        if u and prof and prof.open_to_match:
            out.append({"student_id": u.id, "name": u.full_name, "headline": prof.headline, "skill": b.skill.name,
                        "course": b.course_code, "project": pids[b.project_id].title, "term": b.term})
    return out
