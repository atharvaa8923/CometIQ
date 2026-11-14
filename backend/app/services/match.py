"""CometMatch engine — transparent student ↔ job skill matching.

Student skill level (0–1) per skill, best of:
  resume evidence            1.0
  completed course (graph)   course-skill weight (1.0 core topic, 0.6 secondary)
  enrolled course            0.5 × weight   (in progress)
  verified evidence (course / certification / project, checked by an admin or advisor)  1.0
  pending evidence (self-reported, not yet verified)  0.5
Base fit = Σ w·min(level,1) / Σ w × 100, with w = 1.0 required, 0.5 preferred.
Bonus  = verified certification/project points whose skills the job asks for (capped at +15).
Fit    = min(100, base + bonus). Nothing else is hidden; every point is explained in the breakdown.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill, Evidence, Job, Skill, StudentCourse, StudentProfile
from .gap import IMPORTANCE_W


def student_skills(db: Session, user_id: str) -> dict[int, dict]:
    out: dict[int, dict] = defaultdict(lambda: {"level": 0.0, "sources": []})
    prof = db.get(StudentProfile, user_id)
    for sid in (prof.resume_skills if prof else []) or []:
        out[sid]["level"] = 1.0
        out[sid]["sources"].append("Resume")
    rows = db.execute(select(StudentCourse.status, Course.code, CourseSkill.skill_id, CourseSkill.weight)
                      .join(Course, Course.id == StudentCourse.course_id)
                      .join(CourseSkill, CourseSkill.course_id == Course.id)
                      .where(StudentCourse.user_id == user_id, StudentCourse.status.in_(("completed", "enrolled")))).all()
    for status, code, sid, w in rows:
        lvl = w if status == "completed" else 0.5 * w
        out[sid]["level"] = max(out[sid]["level"], lvl)
        out[sid]["sources"].append(code if status == "completed" else f"{code} (in progress)")
    for e in db.scalars(select(Evidence).where(Evidence.student_id == user_id, Evidence.status.in_(("verified", "pending")))):
        lvl = 1.0 if e.status == "verified" else 0.5
        for sid in e.skills or []:
            out[sid]["level"] = max(out[sid]["level"], lvl)
            out[sid]["sources"].append(f"✓ {e.title}" if e.status == "verified" else f"{e.title} (pending verification)")
    return dict(out)


BONUS_CAP = 15


def student_bonuses(db: Session, user_id: str) -> list[dict]:
    return [{"title": e.title, "kind": e.kind, "points": e.bonus_points, "skills": set(e.skills or [])}
            for e in db.scalars(select(Evidence).where(Evidence.student_id == user_id, Evidence.status == "verified",
                                                        Evidence.bonus_points > 0))]


def student_profile(db: Session, user_id: str) -> tuple[dict[int, dict], list[dict]]:
    return student_skills(db, user_id), student_bonuses(db, user_id)


def fit_label(score: float) -> str:
    return "Strong fit" if score >= 70 else "Good fit" if score >= 50 else "Stretch" if score >= 30 else "Low fit"


def score_job(job: Job, skills: dict[int, dict], teach: dict[int, list[str]] | None = None,
              bonuses: list[dict] | None = None) -> dict:
    matched, partial, missing = [], [], []
    total = earned = 0.0
    for js in job.skills:
        w = IMPORTANCE_W.get(js.importance, 1.0)
        lvl = min(skills.get(js.skill_id, {}).get("level", 0.0), 1.0)
        total += w
        earned += w * lvl
        item = {"skill": js.skill.name, "category": js.skill.category, "importance": js.importance,
                "level": round(lvl, 2), "sources": skills.get(js.skill_id, {}).get("sources", [])[:3]}
        if lvl >= 0.95:
            matched.append(item)
        elif lvl > 0:
            partial.append(item)
        else:
            item["learn_in"] = (teach or {}).get(js.skill_id, [])[:3]
            missing.append(item)
    base = round(100 * earned / total, 1) if total else 0.0
    job_skill_ids = {js.skill_id for js in job.skills}
    applied, bonus = [], 0
    for b in sorted(bonuses or [], key=lambda x: -x["points"]):
        if b["skills"] & job_skill_ids and bonus < BONUS_CAP:
            pts = min(b["points"], BONUS_CAP - bonus)
            bonus += pts
            applied.append({"title": b["title"], "kind": b["kind"], "points": pts})
    score = round(min(100.0, base + bonus), 1)
    order = lambda x: (x["importance"] != "required", x["skill"])  # noqa: E731
    req_missing = [m["skill"] for m in missing if m["importance"] == "required"]
    why = (f"Matches {len(matched)} of {len(job.skills)} skills"
           + (f"; partial on {len(partial)}" if partial else "")
           + (f"; missing required: {', '.join(req_missing[:3])}" if req_missing else "; no required skills missing"))
    if applied:
        why += f"; +{bonus} bonus for verified {', '.join(a['title'] for a in applied)}"
    return {"score": score, "base_score": base, "bonus": bonus, "bonus_items": applied, "label": fit_label(score), "summary": why,
            "matched": sorted(matched, key=order), "partial": sorted(partial, key=order), "missing": sorted(missing, key=order)}


def teaching_courses(db: Session, org_id: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = defaultdict(list)
    for sid, code in db.execute(select(CourseSkill.skill_id, Course.code).join(Course)
                                .where(Course.org_id == org_id, CourseSkill.weight >= 1.0).order_by(Course.code)).all():
        out[sid].append(code)
    return out


def skill_profile(db: Session, user_id: str) -> list[dict]:
    sk = student_skills(db, user_id)
    if not sk:
        return []
    names = {s.id: s for s in db.scalars(select(Skill).where(Skill.id.in_(sk)))}
    return sorted(({"id": sid, "name": names[sid].name, "category": names[sid].category, "level": round(min(v["level"], 1), 2),
                    "sources": list(dict.fromkeys(v["sources"]))} for sid, v in sk.items() if sid in names),
                  key=lambda x: (-x["level"], x["name"]))
