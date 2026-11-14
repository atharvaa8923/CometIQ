"""CometMatch engine — transparent student ↔ job skill matching.

Student skill level (0–1) per skill, best of:
  resume evidence            1.0
  completed course (graph)   course-skill weight (1.0 core topic, 0.6 secondary)
  enrolled course            0.5 × weight   (in progress)
Fit score = Σ w·min(level,1) / Σ w × 100, with w = 1.0 required, 0.5 preferred.
Nothing else is hidden in the score; every point is explained in the breakdown.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill, Job, Skill, StudentCourse, StudentProfile
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
    return dict(out)


def fit_label(score: float) -> str:
    return "Strong fit" if score >= 70 else "Good fit" if score >= 50 else "Stretch" if score >= 30 else "Low fit"


def score_job(job: Job, skills: dict[int, dict], teach: dict[int, list[str]] | None = None) -> dict:
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
    score = round(100 * earned / total, 1) if total else 0.0
    order = lambda x: (x["importance"] != "required", x["skill"])  # noqa: E731
    req_missing = [m["skill"] for m in missing if m["importance"] == "required"]
    why = (f"Matches {len(matched)} of {len(job.skills)} skills"
           + (f"; partial on {len(partial)}" if partial else "")
           + (f"; missing required: {', '.join(req_missing[:3])}" if req_missing else "; no required skills missing"))
    return {"score": score, "label": fit_label(score), "summary": why,
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
