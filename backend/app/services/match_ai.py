"""CometMatch AI: match explanations, resume tips and 'skills to learn next'.

Each feature has a deterministic built-in version; with ANTHROPIC_API_KEY set, Claude writes
the explanation/tips from the same facts (it never changes the numeric score).
"""
import re
from collections import defaultdict

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill, Evidence, Job, Program, StudentCourse, StudentProfile
from . import ai
from .gap import IMPORTANCE_W, market_demand
from .match import score_job, student_profile


# ── Match explanation ──────────────────────────────────────────────────────────
class Explanation(BaseModel):
    headline: str
    strengths: list[str]
    gaps: list[str]
    next_steps: list[str]


def explain(job: Job, m: dict, perspective: str, name: str) -> tuple[Explanation, str]:
    """perspective: 'student' (written to the student) or 'employer' (written about the candidate)."""
    builtin = _explain_builtin(job, m, perspective, name)
    if not ai.enabled():
        return builtin, "builtin"
    def fmt(items, extra):
        return "; ".join(extra(x) for x in items) or "none"

    facts = "\n".join([
        "Job: %s at %s" % (job.title, job.company),
        "Fit score: %s%% (%s); base %s%% + bonus %s" % (m["score"], m["label"], m["base_score"], m["bonus"]),
        "Matched: " + fmt(m["matched"], lambda x: "%s (%s; evidence: %s)" % (x["skill"], x["importance"], ", ".join(x["sources"]) or "n/a")),
        "Partial: " + fmt(m["partial"], lambda x: "%s (%s, level %s)" % (x["skill"], x["importance"], x["level"])),
        "Missing: " + fmt(m["missing"], lambda x: "%s (%s; taught in %s)" % (x["skill"], x["importance"], ", ".join(x.get("learn_in") or []) or "no listed course")),
        "Bonus items: " + (", ".join(b["title"] for b in m["bonus_items"]) or "none"),
    ])
    who = (f"Write directly to the student ({name}) in second person." if perspective == "student"
           else f"Write for a recruiter evaluating the candidate {name}, in third person, neutral and fair.")
    res = ai.structured(
        system=("You explain skill-match results for a university talent platform. Use ONLY the facts given; never invent "
                "experience, numbers or skills. Be specific and encouraging but honest. headline ≤ 25 words; 2–4 items per list, "
                "each ≤ 25 words. next_steps should cite the listed courses or evidence when available."),
        prompt=f"{who}\n\n{facts}", schema=Explanation, effort="low", max_tokens=4000)
    return (res, "claude") if res else (builtin, "builtin")


def _explain_builtin(job: Job, m: dict, perspective: str, name: str) -> Explanation:
    you = "You" if perspective == "student" else name.split()[0]
    req_missing = [x for x in m["missing"] if x["importance"] == "required"]
    strengths = [f"{x['skill']} — shown by {', '.join(x['sources'][:2])}" for x in m["matched"] if x["importance"] == "required"][:4]
    if m["bonus_items"]:
        strengths.append("Verified " + ", ".join(b["title"] for b in m["bonus_items"]) + f" (+{m['bonus']} bonus)")
    gaps = [f"{x['skill']} ({x['importance']})" for x in req_missing[:3]]
    gaps += [f"{x['skill']} is only partly evidenced ({round(x['level'] * 100)}%)" for x in m["partial"][:2]]
    steps = []
    for x in req_missing[:3]:
        if x.get("learn_in"):
            steps.append(f"Take {x['learn_in'][0]} to build {x['skill']}" if perspective == "student"
                         else f"{x['skill']} is taught in {x['learn_in'][0]} — ask whether they have taken it")
        else:
            steps.append(f"Add a project or certification that demonstrates {x['skill']}" if perspective == "student"
                         else f"Probe {x['skill']} in the interview")
    if perspective == "student" and m["partial"]:
        steps.append("Upload proof (certificate or project) for partial skills in Courses & certifications to get them verified")
    level = {"Strong fit": "a strong match", "Good fit": "a good match", "Stretch": "a stretch role", "Low fit": "not yet a close match"}[m["label"]]
    head = (f"{you} {'are' if you == 'You' else 'is'} {level} for {job.title} ({round(m['score'])}%): "
            f"{len(m['matched'])} of {len(m['matched']) + len(m['partial']) + len(m['missing'])} skills evidenced"
            + (f", with {len(req_missing)} required skill{'s' if len(req_missing) != 1 else ''} still missing." if req_missing else " and no required gaps."))
    return Explanation(headline=head, strengths=strengths or ["No required skills evidenced yet"], gaps=gaps or ["No significant gaps"],
                       next_steps=steps or ["Apply — your evidence covers the role's requirements"])


# ── Resume tips ────────────────────────────────────────────────────────────────
class Tip(BaseModel):
    title: str
    detail: str
    priority: str  # high | medium | low


class ResumeReview(BaseModel):
    summary: str
    tips: list[Tip]


_WEAK = re.compile(r"\b(responsible for|worked on|helped with|duties included|tasked with)\b", re.I)
_SECTIONS = {"Experience": r"\bexperience|internship|employment\b", "Education": r"\beducation|university|degree\b",
             "Skills": r"\bskills\b", "Projects": r"\bprojects?\b"}


def resume_review(db: Session, user_id: str, org_id: str) -> tuple[ResumeReview, str]:
    prof = db.get(StudentProfile, user_id)
    text = (prof.resume_text or "") if prof else ""
    goal = prof.career_goal if prof else None
    if not text.strip():
        return ResumeReview(summary="Upload your resume to get personalized tips.",
                            tips=[Tip(title="Upload your resume", detail="CometIQ reads it to find your skills and suggest improvements.", priority="high")]), "builtin"
    skills, _ = student_profile(db, user_id)
    resume_ids = set(prof.resume_skills or [])
    demand, n = market_demand(db, goal, org_id) if goal else ([], 0)
    top = demand[:15]
    tips: list[Tip] = []
    # 1. skills proven elsewhere but missing from the resume
    hidden = [d["name"] for d in top if d["skill_id"] in skills and d["skill_id"] not in resume_ids]
    if hidden:
        tips.append(Tip(title="List skills you already have", priority="high",
                        detail=f"Your courses or verified evidence show {', '.join(hidden[:5])}, but your resume doesn't mention "
                               f"{'it' if len(hidden) == 1 else 'them'}. Recruiters and ATS filters look for these keywords."))
    # 2. verified certifications not on the resume
    certs = [e.title for e in db.scalars(select(Evidence).where(Evidence.student_id == user_id, Evidence.status == "verified",
                                                                Evidence.kind == "certification"))
             if e.title.lower()[:20] not in text.lower()]
    if certs:
        tips.append(Tip(title="Add your verified certifications", priority="high",
                        detail=f"Add a Certifications section with {', '.join(certs[:3])}."))
    # 3. in-demand skills nobody has evidence for yet
    missing = [d["name"] for d in top[:8] if d["skill_id"] not in skills]
    if missing and goal:
        tips.append(Tip(title=f"Close the top {goal} gaps", priority="medium",
                        detail=f"{', '.join(missing[:4])} appear in many {goal} postings ({n} analyzed). See 'Skills to learn next' for courses."))
    # 4. quantified impact
    numbers = len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|percent|k\b|x\b|\+)|\$\s?\d", text, re.I))
    if numbers < 3:
        tips.append(Tip(title="Quantify your impact", priority="high",
                        detail="Only " + str(numbers) + " measurable results found. Add numbers: 'cut report time 40%', 'analyzed 2M rows', 'served 12 stores'."))
    # 5. weak phrasing
    weak = sorted({m.group(0).lower() for m in _WEAK.finditer(text)})
    if weak:
        tips.append(Tip(title="Use strong action verbs", priority="medium",
                        detail=f"Replace '{weak[0]}' with verbs like built, analyzed, automated, led, reduced."))
    # 6. structure & length
    words = len(text.split())
    absent = [k for k, rx in _SECTIONS.items() if not re.search(rx, text, re.I)]
    if absent:
        tips.append(Tip(title="Add standard sections", priority="medium", detail=f"Recruiters expect: {', '.join(absent)}."))
    if words < 150:
        tips.append(Tip(title="Add more detail", priority="medium", detail=f"Your resume has about {words} words; aim for 350–650 with 2–4 bullets per role or project."))
    elif words > 900:
        tips.append(Tip(title="Tighten it to one page", priority="low", detail=f"About {words} words — keep the most relevant, quantified bullets."))
    summary = (f"{len(tips)} improvement{'s' if len(tips) != 1 else ''} found"
               + (f" for {goal} roles" if goal else "") + ". Start with the high-priority items.")
    builtin = ResumeReview(summary=summary, tips=tips or [Tip(title="Looking good", detail="No major issues found.", priority="low")])
    if not ai.enabled():
        return builtin, "builtin"
    res = ai.structured(
        system=("You are a career coach at a business school reviewing a student's resume for a target role. Give 4–7 concrete, "
                "prioritized tips (title ≤ 8 words, detail ≤ 45 words), quoting or pointing to specific lines when useful. Use only the "
                "facts provided; do not invent experience. priority is high, medium or low."),
        prompt=(f"Target role: {goal or 'not set'}\nTop skills employers want: {', '.join(d['name'] for d in top) or 'unknown'}\n"
                f"Skills proven by courses/verified evidence but not on the resume: {', '.join(hidden) or 'none'}\n"
                f"Verified certifications not on the resume: {', '.join(certs) or 'none'}\n\n<resume>\n{text[:20000]}\n</resume>"),
        schema=ResumeReview, effort="medium", max_tokens=6000)
    return (res, "claude") if res else (builtin, "builtin")


# ── Skills to learn next ───────────────────────────────────────────────────────
def learn_next(db: Session, user_id: str, org_id: str, jobs: list[Job], limit: int = 8) -> list[dict]:
    """Rank missing skills by how many points they would add across the student's best-fit jobs."""
    skills, bonuses = student_profile(db, user_id)
    scored = sorted(((score_job(j, skills, bonuses=bonuses)["score"], j) for j in jobs), key=lambda x: -x[0])[:15]
    gain: dict[int, dict] = {}
    for _, j in scored:
        total = sum(IMPORTANCE_W.get(js.importance, 1.0) for js in j.skills) or 1
        for js in j.skills:
            lvl = min(skills.get(js.skill_id, {}).get("level", 0.0), 1.0)
            if lvl >= 0.95:
                continue
            g = gain.setdefault(js.skill_id, {"skill_id": js.skill_id, "skill": js.skill.name, "category": js.skill.category,
                                              "jobs": 0, "points": 0.0, "current_level": lvl, "examples": []})
            g["jobs"] += 1
            g["points"] += 100 * IMPORTANCE_W.get(js.importance, 1.0) * (1 - lvl) / total
            if len(g["examples"]) < 3:
                g["examples"].append(j.title)
    ranked = sorted(gain.values(), key=lambda g: -g["points"])[:limit]
    prof = db.get(StudentProfile, user_id)
    program = db.get(Program, prof.program_id) if prof and prof.program_id else None
    pool = set()
    if program:
        pool = {pc.course_id for pc in program.core} | {cc.course_id for c in program.concentrations for cc in c.courses}
    status = dict(db.execute(select(StudentCourse.course_id, StudentCourse.status).where(StudentCourse.user_id == user_id)).all())
    teach: dict[int, list[Course]] = defaultdict(list)
    for cs, c in db.execute(select(CourseSkill, Course).join(Course).where(
            Course.org_id == org_id, CourseSkill.skill_id.in_([g["skill_id"] for g in ranked]), CourseSkill.weight >= 1.0)).all():
        teach[cs.skill_id].append(c)
    for g in ranked:
        courses = sorted(teach.get(g["skill_id"], []), key=lambda c: (c.id not in pool, c.code))[:4]
        g["points_per_job"] = round(g["points"] / g["jobs"], 1)
        g["points"] = round(g["points"], 1)
        g["courses"] = [{"id": c.id, "code": c.code, "title": c.title, "in_program": c.id in pool, "status": status.get(c.id)} for c in courses]
    return ranked
