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

from ..models import Course, CourseSkill, Evidence, Job, Skill, SkillBadge, StudentCourse, StudentProfile
from .gap import IMPORTANCE_W


def students_skills(db: Session, user_ids: list[str]) -> dict[str, dict[int, dict]]:
    """Skill levels for many students at once (a constant number of queries, whatever the number of students)."""
    ids = list(dict.fromkeys(user_ids))
    out: dict[str, dict[int, dict]] = {u: defaultdict(lambda: {"level": 0.0, "sources": []}) for u in ids}
    if not ids:
        return {}
    for uid, skills in db.execute(select(StudentProfile.user_id, StudentProfile.resume_skills).where(StudentProfile.user_id.in_(ids))):
        for sid in skills or []:
            out[uid][sid]["level"] = 1.0
            out[uid][sid]["sources"].append("Resume")
    rows = db.execute(select(StudentCourse.user_id, StudentCourse.status, Course.code, CourseSkill.skill_id, CourseSkill.weight)
                      .join(Course, Course.id == StudentCourse.course_id)
                      .join(CourseSkill, CourseSkill.course_id == Course.id)
                      .where(StudentCourse.user_id.in_(ids), StudentCourse.status.in_(("completed", "enrolled")))).all()
    for uid, status, code, sid, w in rows:
        lvl = w if status == "completed" else 0.5 * w
        d = out[uid][sid]
        d["level"] = max(d["level"], lvl)
        d["sources"].append(code if status == "completed" else f"{code} (in progress)")
    for e in db.scalars(select(Evidence).where(Evidence.student_id.in_(ids), Evidence.status.in_(("verified", "pending")))):
        lvl = 1.0 if e.status == "verified" else 0.5
        for sid in e.skills or []:
            d = out[e.student_id][sid]
            d["level"] = max(d["level"], lvl)
            d["sources"].append(f"✓ {e.title}" if e.status == "verified" else f"{e.title} (pending verification)")
    codes: dict[tuple[str, int], set[str]] = defaultdict(set)
    for uid, sid, code in db.execute(select(SkillBadge.student_id, SkillBadge.skill_id, SkillBadge.course_code)
                                     .where(SkillBadge.student_id.in_(ids), SkillBadge.status == "active")):
        codes[(uid, sid)].add(code)
    for (uid, sid), cs in codes.items():
        d = out[uid][sid]
        d["level"] = 1.0
        d["faculty_verified"] = True
        d["sources"].insert(0, "★ Faculty-verified in " + ", ".join(sorted(cs)))
    return {u: dict(v) for u, v in out.items()}


def student_skills(db: Session, user_id: str) -> dict[int, dict]:
    return students_skills(db, [user_id])[user_id]


BONUS_CAP = 15


def students_bonuses(db: Session, user_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if user_ids:
        for e in db.scalars(select(Evidence).where(Evidence.student_id.in_(list(set(user_ids))), Evidence.status == "verified",
                                                    Evidence.bonus_points > 0)):
            out[e.student_id].append({"title": e.title, "kind": e.kind, "points": e.bonus_points, "skills": set(e.skills or [])})
    return out


def student_bonuses(db: Session, user_id: str) -> list[dict]:
    return students_bonuses(db, [user_id]).get(user_id, [])


def student_profile(db: Session, user_id: str) -> tuple[dict[int, dict], list[dict]]:
    return student_skills(db, user_id), student_bonuses(db, user_id)


def open_jobs(db: Session, org_id: str) -> list:
    """Open postings visible to an organization, with their skills, as plain read-only records (the shape score_job and
    job_out need). Cached until any posting or the organization's data changes; rebuilding 400 ORM postings with their
    skills on every request was the main cost of the student job list."""
    from types import SimpleNamespace

    from ..routers.jobs import job_out
    from .cache import cached

    def build():
        rows = []
        for j in db.scalars(select(Job).where(Job.is_open, (Job.org_id == org_id) | Job.org_id.is_(None))):
            skills = tuple(SimpleNamespace(skill_id=js.skill_id, importance=js.importance,
                                           skill=SimpleNamespace(id=js.skill.id, name=js.skill.name, category=js.skill.category))
                           for js in j.skills)
            rows.append(SimpleNamespace(id=j.id, title=j.title, company=j.company, role_family=j.role_family,
                                        employment_type=j.employment_type, employer_id=j.employer_id, skills=skills, out=job_out(j)))
        return rows

    return cached(db, org_id, ("open_jobs",), build)


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
