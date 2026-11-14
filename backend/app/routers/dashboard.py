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
