"""Org-wide summary and impact metrics (visible to every signed-in member)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ROLES, Application, Course, ForgeDraft, GapAnalysis, Job, Program, Syllabus, User
from ..security import current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def org_counts(db: Session, org_id: str) -> dict:
    def n(stmt):
        return db.scalar(stmt) or 0

    members = dict(db.execute(select(User.role, func.count()).where(User.org_id == org_id).group_by(User.role)).all())
    return {
        "members": {r: members.get(r, 0) for r in ROLES},
        "courses": n(select(func.count()).select_from(Course).where(Course.org_id == org_id)),
        "programs": n(select(func.count()).select_from(Program).where(Program.org_id == org_id)),
        "syllabi": n(select(func.count()).select_from(Syllabus).where(Syllabus.org_id == org_id)),
        "analyses": n(select(func.count()).select_from(GapAnalysis).join(Syllabus).where(Syllabus.org_id == org_id)),
        "drafts": n(select(func.count()).select_from(ForgeDraft).where(ForgeDraft.org_id == org_id)),
        "jobs": n(select(func.count()).select_from(Job).where(Job.is_open, (Job.org_id == org_id) | Job.org_id.is_(None))),
        "applications": n(select(func.count()).select_from(Application).join(Job).where((Job.org_id == org_id) | Job.org_id.is_(None))),
    }


@router.get("/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return org_counts(db, user.org_id)


@router.get("/impact")
def impact(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Outcome metrics across the whole feedback loop (Industry → Curriculum → Students → Employers)."""
    from collections import Counter

    from ..models import Application, ForgeDraft, StudentCourse, StudentProfile
    from ..services import forge as forgesvc

    org = user.org_id
    # Curricula: latest analysis per syllabus
    latest: dict[str, GapAnalysis] = {}
    for ga in db.scalars(select(GapAnalysis).join(Syllabus).where(Syllabus.org_id == org).order_by(GapAnalysis.created_at)):
        latest[ga.syllabus_id] = ga
    gaps = Counter()
    for ga in latest.values():
        for g in ga.result.get("gaps", []):
            if g["priority"] in ("critical", "high") and g["status"] == "missing":
                gaps[g["name"]] += 1
    drafts = list(db.scalars(select(ForgeDraft).where(ForgeDraft.org_id == org)))
    lifts = []
    for d in drafts:
        ga = db.get(GapAnalysis, d.analysis_id) if d.analysis_id else None
        if ga:
            lifts.append(forgesvc.projected_score(ga.result, set(d.content.get("gaps_addressed", []))) - ga.score)
    # Students
    students = db.scalar(select(func.count()).select_from(User).where(User.org_id == org, User.role == "student")) or 0
    with_goal = db.scalar(select(func.count()).select_from(StudentProfile).join(User, User.id == StudentProfile.user_id)
                          .where(User.org_id == org, StudentProfile.career_goal.is_not(None))) or 0
    with_plan = db.scalar(select(func.count(func.distinct(StudentCourse.user_id))).join(User, User.id == StudentCourse.user_id)
                          .where(User.org_id == org, StudentCourse.status == "planned")) or 0
    goals = Counter(g for (g,) in db.execute(select(StudentProfile.career_goal).join(User, User.id == StudentProfile.user_id)
                                              .where(User.org_id == org, StudentProfile.career_goal.is_not(None))).all())
    # Employers & outcomes
    employers = db.scalar(select(func.count()).select_from(User).where(User.org_id == org, User.role == "employer")) or 0
    posted = db.scalar(select(func.count()).select_from(Job).where(Job.org_id == org, Job.employer_id.is_not(None), Job.is_open)) or 0
    apps = Counter(s for (s,) in db.execute(select(Application.status).join(Job).where(Job.org_id == org)).all())
    avg_fit = db.scalar(select(func.avg(Application.score)).join(Job).where(Job.org_id == org))
    return {
        "curricula": {"syllabi_analyzed": len(latest), "avg_coverage": round(sum(g.score for g in latest.values()) / len(latest), 1) if latest else None,
                      "drafts": len(drafts), "approved": sum(d.status == "approved" for d in drafts),
                      "avg_projected_lift": round(sum(lifts) / len(lifts), 1) if lifts else None,
                      "top_gaps": [{"skill": k, "courses": v} for k, v in gaps.most_common(8)]},
        "students": {"total": students, "with_goal": with_goal, "with_plan": with_plan,
                     "goals": [{"goal": k, "students": v} for k, v in goals.most_common(6)]},
        "employers": {"total": employers, "open_roles": posted},
        "outcomes": {"applications": sum(apps.values()), "shortlisted": apps["shortlisted"], "interviews": apps["interview"],
                     "offers": apps["offer"] + apps["hired"], "avg_fit": round(avg_fit, 1) if avg_fit is not None else None},
    }
