"""CometGap engine — compare what a syllabus teaches with what the job market demands.

Scoring (transparent, reproducible):
  demand(skill)   = weighted share of target postings that ask for the skill
                    (required = 1.0, preferred = 0.5)
  status(skill)   = covered  (≥2 mentions, or named in the course schedule/topics)
                    partial  (mentioned once)
                    missing  (not mentioned)
  coverage score  = Σ demand × {covered 1, partial 0.5, missing 0} / Σ demand   (top-N market skills)
  priority        = critical ≥ 40% of postings · high ≥ 25% · medium ≥ 12% · low otherwise
"""
import math
from collections import defaultdict

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..models import Course, CourseSkill, GapAnalysis, Job, JobSkill, Program, Skill, Syllabus
from . import ai

ALL = "All roles"
IMPORTANCE_W = {"required": 1.0, "preferred": 0.5}
STATUS_W = {"covered": 1.0, "partial": 0.5, "missing": 0.0}

# Suggested teaching activity per skill category (used for built-in recommendations)
ACTIVITY = {
    "Analytics & Data": "a hands-on lab with a real dataset and a short analytic memo",
    "AI & Machine Learning": "a guided notebook lab plus a mini-project applying the technique to a business problem",
    "Software & Cloud": "a tool walkthrough and a graded build exercise in a sandbox environment",
    "Cybersecurity": "a case study plus a controls/threat-modeling exercise",
    "Finance": "a spreadsheet modeling assignment on a real company",
    "Accounting": "a practice set with an applied case and reflection",
    "Information Systems": "a requirements/process-modeling exercise with a client-style deliverable",
    "Marketing": "a campaign analysis assignment using platform data",
    "Operations & Supply Chain": "an operations case with a quantitative model",
    "Management & Strategy": "a case discussion and a short strategy brief",
    "Healthcare": "a healthcare case study with metrics review",
    "Professional Skills": "a team deliverable with a presentation and peer feedback",
}


def priority(demand: float) -> str:
    if demand >= 0.40:
        return "critical"
    if demand >= 0.25:
        return "high"
    if demand >= 0.12:
        return "medium"
    return "low"


def market_job_ids(db: Session, target: str = ALL, org_id: str | None = None) -> list[str]:
    """Open postings visible to the organization, optionally for one role family."""
    jobs = select(Job.id).where(Job.is_open)
    if org_id:
        jobs = jobs.where((Job.org_id == org_id) | Job.org_id.is_(None))
    if target and target != ALL:
        jobs = jobs.where(Job.role_family == target)
    return list(db.scalars(jobs))


def _day(d) -> str | None:
    return d.date().isoformat() if d else None


def market_demand(db: Session, target: str = ALL, org_id: str | None = None,
                  job_ids: list[str] | None = None) -> tuple[list[dict], int]:
    """Skill demand across a set of postings (a frozen sample when job_ids is given, else current open postings),
    with provenance per skill: required/preferred counts, sources and posting-date range."""
    if job_ids is None:
        job_ids = market_job_ids(db, target, org_id)
    n = len(job_ids)
    if not n:
        return [], 0
    rows = db.execute(
        select(Skill, JobSkill.importance, Job.source, Job.posted_at).join(JobSkill, JobSkill.skill_id == Skill.id)
        .join(Job, Job.id == JobSkill.job_id).where(JobSkill.job_id.in_(job_ids))
    ).all()
    agg: dict[int, dict] = {}
    for skill, imp, source, posted in rows:
        a = agg.setdefault(skill.id, {"skill_id": skill.id, "name": skill.name, "category": skill.category,
                                       "is_emerging": skill.is_emerging, "w": 0.0, "jobs": 0, "required": 0,
                                       "sources": defaultdict(int), "first": None, "last": None})
        a["w"] += IMPORTANCE_W.get(imp, 1.0)
        a["jobs"] += 1
        a["required"] += imp == "required"
        a["sources"][source] += 1
        if posted:
            a["first"] = min(a["first"], posted) if a["first"] else posted
            a["last"] = max(a["last"], posted) if a["last"] else posted
    out = []
    for a in agg.values():
        out.append({"skill_id": a["skill_id"], "name": a["name"], "category": a["category"], "is_emerging": a["is_emerging"],
                    "demand": round(a["w"] / n, 4), "job_count": a["jobs"], "job_share": round(a["jobs"] / n, 4),
                    "required_share": round(a["required"] / max(a["jobs"], 1), 4),
                    "required_count": a["required"], "preferred_count": a["jobs"] - a["required"],
                    "sources": dict(sorted(a["sources"].items(), key=lambda kv: -kv[1])),
                    "first_posted": _day(a["first"]), "last_posted": _day(a["last"])})
    out.sort(key=lambda x: (-x["demand"], x["name"]))
    return out, n


def sample_summary(db: Session, job_ids: list[str]) -> dict:
    """Where the postings came from and when: shown with every analysis so the evidence is auditable."""
    rows = db.execute(select(Job.source, Job.posted_at, Job.role_family).where(Job.id.in_(job_ids))).all() if job_ids else []
    sources: dict[str, int] = defaultdict(int)
    roles: dict[str, int] = defaultdict(int)
    dates = [r[1] for r in rows if r[1]]
    for src, _, role in rows:
        sources[src] += 1
        roles[role or "Unclassified"] += 1
    return {"total": len(rows), "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
            "role_families": dict(sorted(roles.items(), key=lambda kv: -kv[1])),
            "date_from": _day(min(dates)) if dates else None, "date_to": _day(max(dates)) if dates else None}


def detect_target(db: Session, skill_names: set[str], org_id: str) -> str:
    """Pick the role family whose demand profile best matches the syllabus (cosine similarity)."""
    best, best_sim = ALL, 0.0
    for fam in ROLE_FAMILIES:
        demand, n = market_demand(db, fam, org_id)
        if n < 2:
            continue
        vec = {d["name"]: d["demand"] for d in demand}
        dot = sum(v for k, v in vec.items() if k in skill_names)
        norm = math.sqrt(sum(v * v for v in vec.values())) * math.sqrt(max(len(skill_names), 1))
        sim = dot / norm if norm else 0
        if sim > best_sim:
            best, best_sim = fam, sim
    return best if best_sim >= 0.12 else ALL


def _other_courses_teaching(db: Session, org_id: str, skill_ids: list[int], exclude: str | None) -> dict[int, list[str]]:
    if not skill_ids:
        return {}
    rows = db.execute(select(CourseSkill.skill_id, Course.code).join(Course, Course.id == CourseSkill.course_id)
                      .where(Course.org_id == org_id, CourseSkill.skill_id.in_(skill_ids), CourseSkill.weight >= 1.0)).all()
    out: dict[int, list[str]] = defaultdict(list)
    for sid, code in rows:
        if code != exclude and len(out[sid]) < 4:
            out[sid].append(code)
    return out


class _AIRec(BaseModel):
    title: str
    detail: str
    skills: list[str]


class _AIInsights(BaseModel):
    summary: str
    recommendations: list[_AIRec]


def analyze(db: Session, syl: Syllabus, target: str | None = None, top_n: int = 30, sample_id: str | None = None,
            user_id: str | None = None, extraction_engine: str = "builtin", change_note: str | None = None) -> GapAnalysis:
    """Score a syllabus against a job sample. All inputs are versioned and recorded on the analysis (see services/versions)."""
    from datetime import datetime, timezone

    from ..models import JobSample
    from . import versions as vs

    sv = vs.ensure_version(db, syl, user_id=user_id, engine=extraction_engine, change_note=change_note)
    sample = db.get(JobSample, sample_id) if sample_id else None
    if sample and sample.org_id != syl.org_id:
        sample = None
    if sample:
        vs.ensure_snapshot(db, sample)
        target = f"Sample: {sample.name}"
    else:
        if not target or target == "auto":
            target = detect_target(db, set(sv.skills), syl.org_id)
        sample = vs.auto_sample(db, syl.org_id, target, market_job_ids(db, target, syl.org_id))
    documented = sample.kind != "auto"
    demand, n_jobs = vs.demand_from_snapshot(sample.snapshot, vs.skill_meta(db))
    cv = vs.catalog_version(db, syl.org_id, syl.code)
    provenance = {**vs.snapshot_summary(sample.snapshot), "captured_at": datetime.now(timezone.utc).isoformat(),
                  "kind": "documented sample" if documented else "live open postings (snapshot saved)",
                  "snapshot_id": sample.id,
                  "sample": {"id": sample.id, "name": sample.name, "method": sample.method, "criteria": sample.criteria,
                             "created_at": sample.created_at.isoformat()} if documented else None,
                  "criteria": None if documented else {"role_family": target, "status": "open postings at time of analysis"}}
    rows, score = vs.score(sv.skills, sv.topics, demand, top_n)
    cat = defaultdict(lambda: {"demand": 0.0, "earned": 0.0, "skills": 0})
    for r in rows:
        c = cat[r["category"]]
        c["demand"] += r["demand"]
        c["earned"] += r["demand"] * STATUS_W[r["status"]]
        c["skills"] += 1
    skills = sv.skills
    gaps = [r for r in rows if r["status"] != "covered"]
    gaps.sort(key=lambda r: (r["status"] != "missing", -r["demand"]))
    elsewhere = _other_courses_teaching(db, syl.org_id, [g["skill_id"] for g in gaps], syl.code)
    for g in gaps:
        g["taught_in"] = elsewhere.get(g["skill_id"], [])

    market_names = {d["name"] for d in demand}
    strengths = sorted(({"name": n, "mentions": s["mentions"], "in_market": n in market_names} for n, s in skills.items()),
                       key=lambda x: (-x["in_market"], -x["mentions"]))
    emerging = [{"name": d["name"], "demand": d["demand"], "status": next((r["status"] for r in rows if r["name"] == d["name"]),
                 "covered" if d["name"] in skills else "missing")} for d in demand if d["is_emerging"]][:10]

    counts = {s: sum(r["status"] == s for r in rows) for s in STATUS_W}
    result = {
        "target": target, "job_count": n_jobs, "top_n": len(rows), "counts": counts, "provenance": provenance,
        "score_basis": "mentions",
        "skills": rows, "gaps": gaps, "strengths": strengths, "emerging": emerging,
        "categories": [{"category": k, "skills": v["skills"], "coverage": round(100 * v["earned"] / v["demand"], 1) if v["demand"] else 0}
                       for k, v in sorted(cat.items(), key=lambda kv: -kv[1]["demand"])],
        "recommendations": _builtin_recommendations(gaps, emerging, n_jobs, target),
        "summary": _builtin_summary(score, counts, gaps, target, n_jobs),
    }
    engine = "builtin"
    ai_res = _ai_insights(syl, result, score)
    if ai_res:
        result["summary"] = ai_res.summary
        result["recommendations"] = [r.model_dump() | {"source": "claude"} for r in ai_res.recommendations]
        engine = "claude"

    ga = GapAnalysis(syllabus_id=syl.id, target=target, score=score, job_count=n_jobs, result=result, engine=engine,
                     sample_id=sample.id, syllabus_version_id=sv.id, catalog_version_id=cv.id if cv else None,
                     scoring_version=vs.SCORING_VERSION, taxonomy_version=vs.taxonomy_version(), top_n=top_n)
    db.add(ga)
    db.flush()
    carry_over_reviews(db, ga)
    from .decisions import detect_implementation

    detect_implementation(db, ga)
    return ga


def _builtin_summary(score, counts, gaps, target, n_jobs) -> str:
    level = "strong" if score >= 70 else "moderate" if score >= 45 else "limited"
    top = ", ".join(g["name"] for g in gaps[:3]) or "none"
    where = f"the {n_jobs} postings in the job sample “{target[8:]}”" if target.startswith("Sample: ") else f"{n_jobs} current {target if target != ALL else ''} postings"
    return (f"Against {where}, this syllabus shows {level} alignment "
            f"({score}%). It fully covers {counts['covered']} of the top {sum(counts.values())} in-demand skills, partially covers "
            f"{counts['partial']}, and misses {counts['missing']}. Highest-impact gaps: {top}.").replace("  ", " ")


def _builtin_recommendations(gaps, emerging, n_jobs, target) -> list[dict]:
    recs = []
    for g in [g for g in gaps if g["priority"] in ("critical", "high")][:5]:
        act = ACTIVITY.get(g["category"], "a focused module with an applied assignment")
        where = f" It is already taught in {', '.join(g['taught_in'])} — consider a prerequisite link or shared materials." if g["taught_in"] else ""
        verb = "Add" if g["status"] == "missing" else "Deepen"
        recs.append({"title": f"{verb} {g['name']}",
                     "detail": f"{round(g['demand'] * 100)}% weighted demand across {n_jobs} {('sampled' if target.startswith('Sample: ') else target)} postings "
                               f"({g['priority']} priority). Suggested: {act}.{where}",
                     "skills": [g["name"]], "source": "builtin"})
    em_missing = [e["name"] for e in emerging if e["status"] != "covered"]
    if em_missing:
        recs.append({"title": "Introduce emerging technologies",
                     "detail": f"Employers increasingly ask for {', '.join(em_missing[:4])}. A one-week module or guest lecture "
                               "keeps the course future-ready.", "skills": em_missing[:4], "source": "builtin"})
    if not recs:
        recs.append({"title": "Maintain alignment", "detail": "The course already covers the highest-demand skills. Re-run the analysis each term as postings change.",
                     "skills": [], "source": "builtin"})
    return recs


def _ai_insights(syl: Syllabus, result: dict, score: float) -> _AIInsights | None:
    if not ai.enabled():
        return None
    gaps = "\n".join(f"- {g['name']} ({g['category']}): {g['status']}, demand {round(g['demand']*100)}%, priority {g['priority']}"
                     + (f", also taught in {', '.join(g['taught_in'])}" if g["taught_in"] else "") for g in result["gaps"][:15])
    covered = ", ".join(r["name"] for r in result["skills"] if r["status"] == "covered")
    return ai.structured(
        system="You are a curriculum strategist helping university faculty align courses with industry demand. Be specific, practical and concise. Never invent statistics; use only the numbers provided.",
        prompt=(f"Course: {syl.code or ''} {syl.title}\nTarget roles: {result['target']} ({result['job_count']} postings)\n"
                f"Coverage score: {score}%\nCovered skills: {covered or 'none'}\nGaps:\n{gaps}\n\n"
                f"Course topics: {'; '.join(syl.topics[:25]) if syl.topics else 'not listed'}\n\n"
                "Write a 2–3 sentence summary for the faculty member, then 3–6 prioritized, actionable recommendations "
                "(title ≤ 8 words; detail ≤ 60 words naming a concrete module, assignment or project; skills = taxonomy names from the gaps list)."),
        schema=_AIInsights, effort="medium", max_tokens=8000,
    )


def program_heatmap(db: Session, program: Program, target: str, top_n: int = 20) -> dict:
    demand, n = market_demand(db, target, program.org_id)
    market = demand[:top_n]
    courses: dict[str, Course] = {}
    for pc in program.core:
        courses[pc.course.code] = pc.course
    for conc in program.concentrations:
        for cc in conc.courses:
            courses.setdefault(cc.course.code, cc.course)
    course_list = sorted(courses.values(), key=lambda c: c.code)
    core_codes = {pc.course.code for pc in program.core}
    # syllabus-derived skills override catalog when a syllabus is linked to the course
    syl_skills: dict[str, dict[int, float]] = defaultdict(dict)
    for s in db.scalars(select(Syllabus).where(Syllabus.org_id == program.org_id, Syllabus.course_id.in_([c.id for c in course_list]))):
        for ss in s.skills:
            syl_skills[s.course_id][ss.skill_id] = 1.0 if ss.mentions >= 2 else 0.5
    matrix, covered_any = [], defaultdict(float)
    for c in course_list:
        weights = syl_skills.get(c.id) or {cs.skill_id: (1.0 if cs.weight >= 1 else 0.5) for cs in c.skills}
        cells = [weights.get(d["skill_id"], 0.0) for d in market]
        for d, w in zip(market, cells):
            covered_any[d["skill_id"]] = max(covered_any[d["skill_id"]], w)
        matrix.append({"code": c.code, "title": c.title, "id": c.id, "is_core": c.code in core_codes,
                       "source": "syllabus" if c.id in syl_skills else "catalog", "cells": cells})
    total = sum(d["demand"] for d in market) or 1
    score = round(100 * sum(d["demand"] * covered_any[d["skill_id"]] for d in market) / total, 1)
    return {"program": program.name, "target": target, "job_count": n, "score": score,
            "skills": [{**d, "program_coverage": covered_any[d["skill_id"]]} for d in market], "courses": matrix}


# ── Faculty review ─────────────────────────────────────────────────────────────
# The system only detects mentions. Faculty decide whether students practice or demonstrate the skill.
FACULTY_STATUSES = {
    "practiced": "Students practice or demonstrate it (assessed)",
    "mentioned_only": "Mentioned or introduced, not practiced",
    "not_covered": "Not covered",
    "not_relevant": "Not relevant to this course",
}
IMPLIED = {"covered": "practiced", "partial": "mentioned_only", "missing": "not_covered"}  # what each mention signal suggests
FACULTY_W = {"practiced": 1.0, "mentioned_only": 0.5, "not_covered": 0.0}


def decision_for(system_status: str, faculty_status: str) -> str:
    return "confirmed" if IMPLIED.get(system_status) == faculty_status else "corrected"


def review_summary(result: dict, reviews: dict[int, "object"]) -> dict:
    """Mention-based vs faculty-reviewed coverage. Reviewed score uses faculty classifications where they exist
    (not-relevant skills leave the denominator) and the mention signal elsewhere."""
    rows = result.get("skills", [])
    total = earned = reviewed_w = 0.0
    counts = {"reviewed": 0, "confirmed": 0, "corrected": 0, "planned": 0, "done": 0, "not_relevant": 0}
    for r in rows:
        rv = reviews.get(r["skill_id"])
        if rv:
            counts["reviewed"] += 1
            counts[rv.decision] += 1
            if rv.action in ("planned", "done"):
                counts[rv.action] += 1
            if rv.faculty_status == "not_relevant":
                counts["not_relevant"] += 1
                continue
            w = FACULTY_W[rv.faculty_status]
            reviewed_w += r["demand"]
        else:
            w = STATUS_W[r["status"]]
        total += r["demand"]
        earned += r["demand"] * w
    demand_all = sum(r["demand"] for r in rows) or 1
    gaps = [r for r in rows if r["status"] != "covered"]
    return {**counts, "total": len(rows), "gaps_total": len(gaps),
            "gaps_reviewed": sum(1 for g in gaps if g["skill_id"] in reviews),
            "reviewed_score": round(100 * earned / total, 1) if total else None,
            "reviewed_demand_share": round(100 * (reviewed_w + sum(r["demand"] for r in rows if (rv := reviews.get(r["skill_id"])) and rv.faculty_status == "not_relevant")) / demand_all, 1)}


def carry_over_reviews(db: Session, ga: GapAnalysis) -> int:
    """Re-running an analysis keeps faculty judgments for skills that are still in the report."""
    from ..models import GapReview

    prev = db.scalar(select(GapAnalysis).where(GapAnalysis.syllabus_id == ga.syllabus_id, GapAnalysis.id != ga.id,
                                               GapAnalysis.target == ga.target).order_by(GapAnalysis.created_at.desc()).limit(1))
    if not prev:
        return 0
    status = {r["skill_id"]: r["status"] for r in ga.result.get("skills", [])}
    n = 0
    for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == prev.id)):
        if rv.skill_id in status:
            db.add(GapReview(analysis_id=ga.id, skill_id=rv.skill_id, reviewer_id=rv.reviewer_id, system_status=status[rv.skill_id],
                             faculty_status=rv.faculty_status, decision=decision_for(status[rv.skill_id], rv.faculty_status),
                             rationale=rv.rationale, action=rv.action, action_note=rv.action_note, carried_from=prev.id))
            n += 1
    db.flush()
    return n
