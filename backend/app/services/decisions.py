"""Faculty decisions on reviewed gaps, linked to CometForge drafts and checked against later syllabus versions."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Course, ForgeDraft, GapAnalysis, GapDecision, GapReview, JobSample, Syllabus, User
from . import versions as vs

DECISIONS = {
    "add_here": "Add to this course",
    "covered_elsewhere": "Covered elsewhere in the program",
    "defer": "Defer to a later revision",
    "out_of_scope": "Out of scope for this course",
}
ACTIVE = ("open", "drafted", "implemented")


def evidence_for(db: Session, ga: GapAnalysis, row: dict, review: GapReview) -> dict:
    """Exactly which inputs a decision was based on."""
    sv = db.get(vs.SyllabusVersion, ga.syllabus_version_id) if ga.syllabus_version_id else None
    smp = db.get(JobSample, ga.sample_id) if ga.sample_id else None
    cv = db.get(vs.CatalogVersion, ga.catalog_version_id) if ga.catalog_version_id else None
    return {
        "analysis_id": ga.id, "analysis_date": ga.created_at.isoformat(), "score": ga.score,
        "syllabus_version": sv.version if sv else None, "syllabus_semester": sv.semester if sv else None,
        "syllabus_hash": sv.text_hash[:12] if sv else None,
        "sample_id": smp.id if smp else None, "sample_name": smp.name if smp else ga.target, "sample_kind": smp.kind if smp else None,
        "sample_hash": (smp.content_hash or "")[:12] if smp else None,
        "catalog_version_id": cv.id if cv else None, "catalog_year": cv.catalog_year if cv else None,
        "scoring_version": ga.scoring_version, "taxonomy_version": ga.taxonomy_version,
        "system_status": row["status"], "mentions": row["mentions"], "postings_requesting": row["job_count"],
        "postings_in_sample": ga.job_count, "priority": row["priority"],
        "faculty_status": review.faculty_status, "review_rationale": review.rationale,
    }


def out(d: GapDecision) -> dict:
    return {"id": d.id, "syllabus_id": d.syllabus_id, "skill_id": d.skill_id, "skill": d.skill.name if d.skill else None,
            "analysis_id": d.analysis_id, "decision": d.decision, "decision_label": DECISIONS.get(d.decision, d.decision),
            "rationale": d.rationale, "covered_in": d.covered_in or [], "revisit_term": d.revisit_term,
            "reviewer": d.reviewer_name or ("Former faculty member" if not d.reviewer_id else None),
            "decided_at": d.decided_at, "evidence": d.evidence, "status": d.status, "forge_draft_id": d.forge_draft_id,
            "detected_in_version": d.detected_in_version, "implemented_note": d.implemented_note, "superseded_by": d.superseded_by}


def active_for(db: Session, syllabus_id: str) -> dict[int, GapDecision]:
    rows = db.scalars(select(GapDecision).where(GapDecision.syllabus_id == syllabus_id, GapDecision.status.in_(ACTIVE)))
    return {d.skill_id: d for d in rows}


def record(db: Session, user: User, syl: Syllabus, ga: GapAnalysis, skill_id: int, decision: str, rationale: str,
           covered_in: list[str] | None, revisit_term: str | None) -> GapDecision:
    row = next((r for r in ga.result.get("skills", []) if r["skill_id"] == skill_id), None)
    if not row:
        raise HTTPException(404, "Skill is not part of this analysis")
    review = db.scalar(select(GapReview).where(GapReview.analysis_id == ga.id, GapReview.skill_id == skill_id))
    if not review:
        raise HTTPException(400, "Review this gap first: record whether students practice the skill, then decide what to do")
    if review.faculty_status == "practiced":
        raise HTTPException(400, "Faculty classified this skill as practiced, so there is no gap to decide on")
    if decision not in DECISIONS:
        raise HTTPException(400, f"decision must be one of {', '.join(DECISIONS)}")
    rationale = (rationale or "").strip()
    if len(rationale) < 10:
        raise HTTPException(400, "Write the rationale for this decision (at least a short sentence)")
    codes: list[str] = []
    if decision == "covered_elsewhere":
        codes = sorted({c.strip().upper() for c in (covered_in or []) if c.strip()})
        if not codes:
            raise HTTPException(400, "Name the course(s) that cover this skill")
        known = set(db.scalars(select(Course.code).where(Course.org_id == syl.org_id, func.upper(Course.code).in_(codes))))
        unknown = [c for c in codes if c not in known]
        if unknown:
            raise HTTPException(400, f"Not in the catalog: {', '.join(unknown)}")
        if syl.code and syl.code.upper() in codes:
            raise HTTPException(400, "Choose a course other than this one")
    if decision == "defer" and len((revisit_term or "").strip()) < 4:
        raise HTTPException(400, "Say when to revisit it, e.g. Fall 2027")
    d = GapDecision(org_id=syl.org_id, syllabus_id=syl.id, skill_id=skill_id, analysis_id=ga.id, decision=decision,
                    rationale=rationale, covered_in=codes or None,
                    revisit_term=((revisit_term or "").strip() or None) if decision == "defer" else None,
                    reviewer_id=user.id, reviewer_name=user.full_name, evidence=evidence_for(db, ga, row, review), status="open")
    db.add(d)
    db.flush()
    for prev in db.scalars(select(GapDecision).where(GapDecision.syllabus_id == syl.id, GapDecision.skill_id == skill_id,
                                                     GapDecision.id != d.id, GapDecision.status.in_(ACTIVE))):
        prev.status, prev.superseded_by = "superseded", d.id
    return d


def detect_implementation(db: Session, ga: GapAnalysis) -> int:
    """After a new syllabus version is analyzed: flag accepted additions that the mention signal now finds.
    Faculty still confirm; nothing is marked implemented automatically."""
    sv = db.get(vs.SyllabusVersion, ga.syllabus_version_id) if ga.syllabus_version_id else None
    if not sv:
        return 0
    status = {r["skill_id"]: r["status"] for r in ga.result.get("skills", [])}
    n = 0
    for d in db.scalars(select(GapDecision).where(GapDecision.syllabus_id == ga.syllabus_id, GapDecision.decision == "add_here",
                                                  GapDecision.status.in_(("open", "drafted")))):
        decided_v = (d.evidence or {}).get("syllabus_version") or 0
        if sv.version > decided_v and status.get(d.skill_id) == "covered" and d.detected_in_version is None:
            d.detected_in_version = sv.version
            n += 1
    return n


def _skill_lines(text: str, names: list[str]) -> list[dict]:
    from .skills import _matchers

    pats = [(n, p) for n, p in _matchers() if n in set(names)]
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        hits = [n for n, ps in pats if any(p.search(line) for p in ps)]
        out.append({"n": i, "text": line.rstrip(), "skills": hits})
    return out


def proposed_changes(db: Session, syl: Syllabus, draft: ForgeDraft | None, decisions: list[GapDecision]) -> dict:
    """Current syllabus beside the proposed CometForge draft, focused on the accepted additions."""
    sv = vs.latest_version(db, syl.id)
    names = [d.skill.name for d in decisions]
    text = sv.raw_text if sv else syl.raw_text
    current_skills = sv.skills if sv else vs.skills_snapshot(syl)
    c = (draft.content if draft else None) or {}
    per_skill = []
    for d in decisions:
        n = d.skill.name
        per_skill.append({
            "decision_id": d.id, "skill": n, "status": d.status, "rationale": d.rationale,
            "current": current_skills.get(n, {}).get("excerpts", []),
            "proposed": {
                "outcomes": [o for o in c.get("learning_outcomes", []) if n in o.get("skills", [])],
                "modules": [{"week": m["week"], "title": m["title"], "topics": m.get("topics", []), "activities": m.get("activities", []),
                             "is_new": m.get("is_new", False)} for m in c.get("modules", []) if n in m.get("skills", [])],
                "assessments": [a for a in c.get("assessments", []) if n in a.get("skills", [])],
                "project": c.get("project") if n in (c.get("project") or {}).get("skills", []) else None,
            },
        })
    return {
        "syllabus": {"id": syl.id, "code": syl.code, "title": syl.title, "version": sv.version if sv else None,
                     "semester": sv.semester if sv else syl.semester},
        "draft": {"id": draft.id, "version": draft.version, "status": draft.status, "created_at": draft.created_at,
                  "content": c} if draft else None,
        "skills": per_skill,
        "current_lines": _skill_lines(text, names)[:600],
    }
