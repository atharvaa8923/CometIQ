"""Faculty-verified skill badges and outcome tracking.

A student earns a badge for skill S from course C when BOTH hold:
  1. faculty confirmed that C has students practice or master S — a "practiced" CometGap review of C's latest syllabus,
     or a P/M entry for C in a program curriculum map; and
  2. the student's completion of C was verified by an advisor or administrator (verified course evidence), without a
     failing grade on record.
Badges are historical records: they are not withdrawn automatically when a later review changes; an administrator can revoke one.
"""
import re
import secrets
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (Application, Course, CurriculumMapEntry, Evidence, GapDecision, GapReview, JobSkill, Skill, SkillBadge,
                      StudentCourse, Syllabus, SyllabusVersion, User)

FAILING = {"F", "D", "D+", "D-", "W", "I", "U", "NC", "NF", "WF"}


def term_key(term: str | None) -> tuple[int, int] | None:
    """'Fall 2026' → (2026, 3); '2026-05' → (2026, 2). Spring=1, Summer=2, Fall=3."""
    if not term:
        return None
    t = term.strip().lower()
    m = re.search(r"(spring|summer|fall|winter)\s*(20\d\d)", t)
    if m:
        return int(m.group(2)), {"winter": 1, "spring": 1, "summer": 2, "fall": 3}[m.group(1)]
    m = re.match(r"(20\d\d)-(\d\d)", t)
    if m:
        mo = int(m.group(2))
        return int(m.group(1)), 1 if mo <= 5 else 2 if mo <= 7 else 3
    return None


def faculty_basis(db: Session, org_id: str) -> dict[str, dict[int, dict]]:
    """{course_id: {skill_id: {"level", "source", ...}}} — what faculty have confirmed each course teaches."""
    out: dict[str, dict[int, dict]] = defaultdict(dict)
    courses = {c.code.upper(): c.id for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    seen: set[str] = set()
    for syl in db.scalars(select(Syllabus).where(Syllabus.org_id == org_id).order_by(Syllabus.created_at.desc())):
        cid = syl.course_id or courses.get((syl.code or "").upper())
        if not cid or cid in seen or not syl.analyses:
            continue
        seen.add(cid)  # the most recent syllabus of each course
        ga = syl.analyses[0]
        sv = db.get(SyllabusVersion, ga.syllabus_version_id) if ga.syllabus_version_id else None
        for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id, GapReview.faculty_status == "practiced")):
            out[cid][rv.skill_id] = {"level": "practiced", "source": "faculty review", "syllabus_id": syl.id,
                                     "syllabus_version": sv.version if sv else None, "syllabus_semester": sv.semester if sv else syl.semester,
                                     "confirmed_by": rv.reviewer.full_name if rv.reviewer else None,
                                     "confirmed_at": rv.updated_at.isoformat() if rv.updated_at else None}
    for e in db.scalars(select(CurriculumMapEntry).where(CurriculumMapEntry.org_id == org_id, CurriculumMapEntry.level.in_(("P", "M")))):
        lvl = "mastered" if e.level == "M" else "practiced"
        cur = out[e.course_id].get(e.skill_id)
        if cur and cur["level"] == "mastered" and lvl == "practiced":
            continue
        out[e.course_id][e.skill_id] = {"level": lvl, "source": "curriculum map", "confirmed_by": e.set_by_name,
                                        "confirmed_at": e.updated_at.isoformat() if e.updated_at else None, "rationale": e.rationale}
    return out


def verified_completions(db: Session, org_id: str, student_id: str | None = None) -> list[dict]:
    q = select(Evidence).where(Evidence.org_id == org_id, Evidence.kind == "course", Evidence.status == "verified", Evidence.course_id.is_not(None))
    if student_id:
        q = q.where(Evidence.student_id == student_id)
    grades = {(sc.user_id, sc.course_id): sc for sc in db.scalars(select(StudentCourse))}
    out = []
    for e in db.scalars(q):
        sc = grades.get((e.student_id, e.course_id))
        if sc and sc.grade and sc.grade.strip().upper() in FAILING:
            continue
        reviewer = db.get(User, e.reviewer_id) if e.reviewer_id else None
        out.append({"student_id": e.student_id, "course_id": e.course_id, "term": e.issued_on or (sc.term if sc else None),  # the advisor-verified term wins over the self-reported plan
                    "evidence_id": e.id, "verified_by": reviewer.full_name if reviewer else None,
                    "verified_at": e.reviewed_at.isoformat() if e.reviewed_at else None})
    return out


def sync(db: Session, org_id: str, student_id: str | None = None) -> int:
    """Issue every badge that is now earned. Idempotent."""
    basis = faculty_basis(db, org_id)
    have = {(b.student_id, b.skill_id, b.course_id) for b in db.scalars(select(SkillBadge).where(SkillBadge.org_id == org_id))}
    codes = {c.id: c.code for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    n = 0
    for comp in verified_completions(db, org_id, student_id):
        for sid, b in basis.get(comp["course_id"], {}).items():
            key = (comp["student_id"], sid, comp["course_id"])
            if key in have:
                continue
            db.add(SkillBadge(org_id=org_id, student_id=comp["student_id"], skill_id=sid, course_id=comp["course_id"],
                              course_code=codes.get(comp["course_id"], ""), level=b["level"], term=comp["term"],
                              basis={"faculty": b, "completion": {k: comp[k] for k in ("evidence_id", "verified_by", "verified_at", "term")}},
                              public_token=secrets.token_urlsafe(18)))
            have.add(key)
            n += 1
    db.flush()
    return n


def out(b: SkillBadge, public: bool = False) -> dict:
    f, c = (b.basis or {}).get("faculty", {}), (b.basis or {}).get("completion", {})
    d = {"id": b.id, "skill": b.skill.name, "category": b.skill.category, "course_code": b.course_code,
         "course_title": b.course.title if b.course else None, "level": b.level, "term": b.term, "issued_at": b.issued_at,
         "status": b.status, "basis": {"source": f.get("source"), "syllabus_semester": f.get("syllabus_semester"),
                                       "syllabus_version": f.get("syllabus_version"), "confirmed_at": f.get("confirmed_at")}}
    if not public:
        d |= {"public": b.public, "public_token": b.public_token, "revoked_reason": b.revoked_reason,
              "basis": d["basis"] | {"confirmed_by": f.get("confirmed_by"), "completion_verified_by": c.get("verified_by"),
                                     "completion_verified_at": c.get("verified_at")}}
    return d


def badges_by_skill(db: Session, student_id: str) -> dict[int, list[SkillBadge]]:
    out_: dict[int, list[SkillBadge]] = defaultdict(list)
    for b in db.scalars(select(SkillBadge).where(SkillBadge.student_id == student_id, SkillBadge.status == "active")):
        out_[b.skill_id].append(b)
    return out_


# ── Outcomes: did an implemented change make a difference? ────────────────────
def _change_term(db: Session, d: GapDecision) -> str | None:
    if d.detected_in_version:
        v = db.scalar(select(SyllabusVersion).where(SyllabusVersion.syllabus_id == d.syllabus_id, SyllabusVersion.version == d.detected_in_version))
        if v and v.semester:
            return v.semester
    from ..models import CurriculumProposal

    for p in db.scalars(select(CurriculumProposal).where(CurriculumProposal.syllabus_id == d.syllabus_id, CurriculumProposal.status == "adopted")):
        if d.id in (p.decision_ids or []) and p.effective_term:
            return p.effective_term
    return None


def outcomes(db: Session, d: GapDecision) -> dict:
    """Compare students who completed the course before and after the change, in aggregate only.
    Groups smaller than OUTCOME_MIN_COHORT are suppressed so no individual can be identified."""
    k = get_settings().OUTCOME_MIN_COHORT
    syl = db.get(Syllabus, d.syllabus_id)
    course_id = syl.course_id or db.scalar(select(Course.id).where(Course.org_id == d.org_id, func.upper(Course.code) == (syl.code or "").upper()))
    change = _change_term(db, d)
    base = {"decision_id": d.id, "skill": d.skill.name, "course": syl.code, "change_term": change, "min_group": k,
            "caveat": "Observational comparison of different student groups, not proof that the change caused any difference."}
    if d.decision != "add_here":
        return base | {"available": False, "reason": "Outcomes are tracked for changes added to this course."}
    if not change or not term_key(change):
        return base | {"available": False, "reason": "Not implemented yet: the change has no semester (implement it in a new syllabus version or adopt a proposal)."}
    ck = term_key(change)
    comps = [c for c in verified_completions(db, d.org_id) if c["course_id"] == course_id and term_key(c["term"])]
    groups = {"before": [c["student_id"] for c in comps if term_key(c["term"]) < ck], "after": [c["student_id"] for c in comps if term_key(c["term"]) >= ck]}
    req_jobs = set(db.scalars(select(JobSkill.job_id).where(JobSkill.skill_id == d.skill_id, JobSkill.importance == "required")))

    def metrics(ids: list[str]) -> dict:
        n = len(set(ids))
        if n < k:
            return {"students": f"fewer than {k}", "suppressed": True}
        ids = list(set(ids))
        with_badge = db.scalar(select(func.count(func.distinct(SkillBadge.student_id))).where(
            SkillBadge.student_id.in_(ids), SkillBadge.skill_id == d.skill_id, SkillBadge.status == "active")) or 0
        apps = list(db.scalars(select(Application).where(Application.student_id.in_(ids), Application.job_id.in_(req_jobs)))) if req_jobs else []
        m = {"students": n, "suppressed": False, "badge_rate": round(100 * with_badge / n, 1), "applications": len(apps)}
        if len(apps) >= k:
            m["interview_or_offer_rate"] = round(100 * sum(a.status in ("interview", "offer") for a in apps) / len(apps), 1)
        else:
            m["interview_or_offer_rate"] = None
            m["applications_note"] = f"fewer than {k} applications to jobs requiring {d.skill.name}"
        return m

    return base | {"available": True, "before": metrics(groups["before"]), "after": metrics(groups["after"])}


def skill_supply(db: Session, org_id: str) -> list[dict]:
    rows = db.execute(select(Skill.name, func.count(func.distinct(SkillBadge.student_id))).join(Skill, Skill.id == SkillBadge.skill_id)
                      .where(SkillBadge.org_id == org_id, SkillBadge.status == "active").group_by(Skill.name)).all()
    return sorted(({"skill": n, "students": c} for n, c in rows), key=lambda x: -x["students"])

