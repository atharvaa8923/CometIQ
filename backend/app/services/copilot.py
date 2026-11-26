"""Syllabus copilot: re-score an edited syllabus as faculty type.

The edited text is compared with the course's current syllabus version against the job sample of its latest report, using
the deterministic built-in extractor (fast and repeatable) and the current scoring method. For each skill whose status
changes it returns the point change, the posting evidence, the lines that mention it, and where else the program teaches it.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill, CurriculumMapEntry, Program, Syllabus
from . import gap as gapsvc
from . import parser
from . import versions as vs
from .badges import faculty_basis
from .skills import extract_builtin

STATUS_W = vs.STATUS_W
LEVEL = {"covered": "P", "partial": "I", "missing": "-"}


def _skills(text: str) -> dict:
    return {n: {"mentions": i["mentions"], "excerpts": i.get("excerpts") or []} for n, i in extract_builtin(text).items()}


def _where_else(db: Session, org_id: str, exclude_code: str | None) -> dict[int, list[dict]]:
    """skill_id → other courses where faculty confirmed (review or curriculum map) or the catalog says it is taught."""
    codes = {c.id: c.code for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    out: dict[int, dict[str, dict]] = defaultdict(dict)
    for cid, skills in faculty_basis(db, org_id).items():
        for sid, b in skills.items():
            out[sid][codes.get(cid, "?")] = {"course": codes.get(cid, "?"), "level": "M" if b["level"] == "mastered" else "P", "source": b["source"]}
    for cs in db.scalars(select(CourseSkill).where(CourseSkill.weight >= 1.0, CourseSkill.course_id.in_(list(codes)))):
        code = codes.get(cs.course_id)
        if code and code not in out[cs.skill_id]:
            out[cs.skill_id][code] = {"course": code, "level": "I", "source": "catalog"}
    ex = (exclude_code or "").upper()
    return {sid: sorted((v for k, v in d.items() if k.upper() != ex), key=lambda x: ("MPI".index(x["level"]), x["course"]))[:6] for sid, d in out.items()}


def _programs_with(db: Session, org_id: str, code: str | None) -> list[Program]:
    if not code:
        return []
    from .curriculum_map import program_course_map

    cid = db.scalar(select(Course.id).where(Course.org_id == org_id, Course.code == code))
    pcm = program_course_map(db, org_id)
    return [p for p in db.scalars(select(Program).where(Program.org_id == org_id).order_by(Program.name)) if any(c == cid for c, _ in pcm.get(p.id, []))]


def preview(db: Session, syl: Syllabus, text: str) -> dict:
    ga = syl.analyses[0] if syl.analyses else None
    inp = vs.inputs_of(db, ga) if ga else None
    meta = vs.skill_meta(db)
    if inp:
        snap, top_n, sample_name = inp["sample"].snapshot, inp["top_n"], inp["sample"].name
        base_skills, base_topics, base_label = inp["syllabus_version"].skills, inp["syllabus_version"].topics, f"v{inp['syllabus_version'].version}"
    else:  # older report without recorded inputs: compare with the current live postings and the syllabus as stored
        target = ga.target if ga and not ga.target.startswith("Sample: ") else gapsvc.ALL
        snap = vs.snapshot_jobs(db, gapsvc.market_job_ids(db, target, syl.org_id))
        top_n, sample_name = 30, f"{target} postings (live)"
        base_skills, base_topics, base_label = vs.skills_snapshot(syl), list(syl.topics or []), "current"
    demand, n_jobs = vs.demand_from_snapshot(snap, meta)
    draft_skills, draft_topics = _skills(text), parser.extract_topics(text)
    base_rows, base_score = vs.score(base_skills, base_topics, demand, top_n)
    draft_rows, draft_score = vs.score(draft_skills, draft_topics, demand, top_n)
    total = sum(r["demand"] for r in draft_rows) or 1
    before = {r["name"]: r for r in base_rows}
    elsewhere = None
    changes = []
    for r in draft_rows:
        b = before.get(r["name"])
        if not b or b["status"] == r["status"]:
            continue
        if elsewhere is None:
            elsewhere = _where_else(db, syl.org_id, syl.code)
        changes.append({
            "skill": r["name"], "skill_id": r["skill_id"], "category": r["category"], "from": b["status"], "to": r["status"],
            "points": round(100 * r["demand"] * (STATUS_W[r["status"]] - STATUS_W[b["status"]]) / total, 1),
            "share": round(r["demand"] * 100), "priority": r["priority"], "job_count": r["job_count"], "postings": n_jobs,
            "required_count": r["required_count"], "preferred_count": r["preferred_count"], "sources": r["sources"],
            "first_posted": r["first_posted"], "last_posted": r["last_posted"],
            "mentions_from": b["mentions"], "mentions_to": r["mentions"], "excerpts": r["excerpts"][:3],
            "map_from": LEVEL[b["status"]], "map_to": LEVEL[r["status"]],
            "also_in": elsewhere.get(r["skill_id"], []),
        })
    changes.sort(key=lambda c: -abs(c["points"]))
    market = {d["name"] for d in demand[:top_n]}
    added_outside = sorted(n for n in draft_skills if n not in base_skills and n not in market)
    removed_outside = sorted(n for n in base_skills if n not in draft_skills and n not in market)
    # overlap warning: skills this draft practices that faculty already confirmed elsewhere in the program
    if elsewhere is None:
        elsewhere = _where_else(db, syl.org_id, syl.code)
    overlaps = [{"skill": r["name"], "courses": [x["course"] for x in elsewhere.get(r["skill_id"], []) if x["level"] in ("P", "M")]}
                for r in draft_rows if r["status"] == "covered"]
    overlaps = [o for o in overlaps if o["courses"]]
    entries = list(db.scalars(select(CurriculumMapEntry).where(CurriculumMapEntry.org_id == syl.org_id)))
    return {
        "base": {"label": base_label, "score": base_score}, "draft": {"score": draft_score, "skills_detected": len(draft_skills)},
        "delta": round(draft_score - base_score, 1), "sample": {"name": sample_name, "postings": n_jobs, "top_n": top_n},
        "scoring_version": vs.SCORING_VERSION, "changes": changes,
        "added_outside_top": added_outside[:15], "removed_outside_top": removed_outside[:15],
        "overlaps": overlaps[:10], "programs": [p.name for p in _programs_with(db, syl.org_id, syl.code)][:6],
        "faculty_map_entries": sum(1 for e in entries if e.course_id == syl.course_id),
        "note": "Live preview with the built-in keyword extractor and the current scoring method. Faculty review still decides whether students practice each skill.",
    }
