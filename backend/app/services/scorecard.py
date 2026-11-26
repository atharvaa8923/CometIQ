"""Dean's program scorecard: one view across every program of the institution.

For each program: mention-based coverage of its analyzed courses over time, priority gaps nobody has decided on yet,
proposals waiting for review, in-demand skills that no course takes to mastery, and faculty-verified badges earned.
"""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CurriculumProposal, GapAnalysis, GapDecision, Program, SkillBadge, Syllabus
from . import curriculum_map as cmap
from . import gap as gapsvc

ACTIVE_DECISIONS = ("open", "drafted", "implemented")


def _course_syllabi(db: Session, org_id: str) -> dict[str, list[Syllabus]]:
    """Analyzed syllabi by course code (upper case), newest first."""
    out: dict[str, list[Syllabus]] = defaultdict(list)
    from sqlalchemy.orm import selectinload

    for s in db.scalars(select(Syllabus).options(selectinload(Syllabus.analyses)).where(Syllabus.org_id == org_id).order_by(Syllabus.created_at.desc())):
        if s.code and s.analyses:
            out[s.code.upper()].append(s)
    return out


def _trend(analyses: list[tuple[str, GapAnalysis]]) -> list[dict]:
    """Program average after each analysis event, using the latest score of every course seen so far."""
    latest: dict[str, float] = {}
    points = []
    for code, ga in sorted(analyses, key=lambda x: x[1].created_at):
        latest[code] = ga.score
        points.append({"at": ga.created_at.isoformat(), "score": round(sum(latest.values()) / len(latest), 1), "courses": len(latest)})
    # one point per day is enough for a sparkline
    by_day: dict[str, dict] = {}
    for p in points:
        by_day[p["at"][:10]] = p
    return list(by_day.values())


def build(db: Session, org_id: str, target: str = gapsvc.ALL) -> dict:
    demand = gapsvc.market_demand(db, target, org_id)
    syl_by_code = _course_syllabi(db, org_id)
    decisions = defaultdict(set)
    for d in db.scalars(select(GapDecision).where(GapDecision.org_id == org_id, GapDecision.status.in_(ACTIVE_DECISIONS))):
        decisions[d.syllabus_id].add(d.skill_id)
    waiting = list(db.scalars(select(CurriculumProposal).where(CurriculumProposal.org_id == org_id,
                                                               CurriculumProposal.status.in_(("in_review", "changes_requested", "approved")))))
    syl_ids_waiting = defaultdict(list)
    for p in waiting:
        syl_ids_waiting[p.syllabus_id].append(p)
    rows = []
    pcm = cmap.program_course_map(db, org_id)
    from ..models import Course

    code_of = dict(db.execute(select(Course.id, Course.code).where(Course.org_id == org_id)).all())
    badge_pairs: dict[str, set[str]] = {}
    for cid, stu in db.execute(select(SkillBadge.course_id, SkillBadge.student_id).where(SkillBadge.org_id == org_id, SkillBadge.status == "active")):
        badge_pairs.setdefault(cid, set()).add(stu)
    for prog in db.scalars(select(Program).where(Program.org_id == org_id).order_by(Program.name)):
        courses = pcm.get(prog.id, [])
        codes = {code_of[c].upper() for c, _ in courses if c in code_of}
        core = {code_of[c].upper() for c, is_core in courses if is_core and c in code_of}
        analyzed = {code: syl_by_code[code] for code in codes if code in syl_by_code}
        badges = len(set().union(*[badge_pairs.get(c, set()) for c, _ in courses])) if courses else 0
        base = {"id": prog.id, "name": prog.name, "type": prog.type, "catalog_year": prog.catalog_year,
                "catalog_confirmed": bool(prog.catalog_confirmed_by), "courses": len(courses), "core_courses": len(core),
                "analyzed_courses": len(analyzed), "core_analyzed": len(core & set(analyzed)), "badge_holders": badges}
        if not analyzed:
            rows.append(base | {"active": False})
            continue
        latest = {code: syls[0].analyses[0] for code, syls in analyzed.items()}
        coverage = round(sum(ga.score for ga in latest.values()) / len(latest), 1)
        events = [(code, ga) for code, syls in analyzed.items() for s in syls for ga in s.analyses]
        trend = _trend(events)
        undecided = []
        for code, syls in analyzed.items():
            s, ga = syls[0], latest[code]
            for g in ga.result.get("gaps", []):
                if g["priority"] in ("critical", "high") and g["skill_id"] not in decisions[s.id]:
                    undecided.append({"course": code, "syllabus_id": s.id, "analysis_id": ga.id, "skill": g["name"], "priority": g["priority"],
                                      "share": round(g["demand"] * 100)})
        undecided.sort(key=lambda x: (x["priority"] != "critical", -x["share"]))
        props = [p for code, syls in analyzed.items() for s in syls for p in syl_ids_waiting.get(s.id, [])]
        m = cmap.build(db, prog, target, demand=demand)
        never_mastered = [s["name"] for s in m["skills"] if s["in_market"] and not m["summary"][str(s["id"])]["mastered_in"]]
        never_practiced = [s["name"] for s in m["skills"] if s["in_market"] and not (m["summary"][str(s["id"])]["practiced_in"] or m["summary"][str(s["id"])]["mastered_in"])]
        attention = []
        if undecided:
            attention.append(f"{len(undecided)} priority gaps without a decision")
        if props:
            attention.append(f"{len(props)} proposal{'s' if len(props) != 1 else ''} waiting")
        if never_practiced:
            attention.append(f"{len(never_practiced)} in-demand skills never practiced")
        if len(core & set(analyzed)) < len(core):
            attention.append(f"{len(core) - len(core & set(analyzed))} core courses not analyzed")
        if not prog.catalog_confirmed_by:
            attention.append("catalog year not confirmed")
        rows.append(base | {
            "active": True, "coverage": coverage, "trend": trend,
            "coverage_change": round(trend[-1]["score"] - trend[0]["score"], 1) if len(trend) > 1 else 0.0,
            "undecided_gaps": undecided[:25], "undecided_count": len(undecided),
            "proposals_waiting": [{"id": p.id, "number": p.number, "title": p.title, "status": p.status,
                                   "tally": {"approvals": sum(r.vote == "approve" for r in p.reviews if r.revision == p.revision),
                                             "required": p.required_approvals}} for p in props],
            "never_mastered": never_mastered, "never_practiced": never_practiced, "skills_mapped": sum(1 for s in m["skills"] if s["in_market"]),
            "courses_detail": [{"code": code, "syllabus_id": syls[0].id, "analysis_id": latest[code].id, "score": latest[code].score,
                                "is_core": code in core} for code, syls in sorted(analyzed.items())],
            "attention": attention,
        })
    active = [r for r in rows if r["active"]]
    return {
        "target": target, "job_count": demand[1],
        "programs": sorted(active, key=lambda r: (-len(r["attention"]), r["coverage"])) + [r for r in rows if not r["active"]],
        "totals": {"programs": len(rows), "active_programs": len(active),
                   "undecided_gaps": sum(r["undecided_count"] for r in active),
                   "proposals_waiting": len(waiting),
                   "badge_holders": db.scalar(select(func.count(func.distinct(SkillBadge.student_id))).where(
                       SkillBadge.org_id == org_id, SkillBadge.status == "active")) or 0,
                   "avg_coverage": round(sum(r["coverage"] for r in active) / len(active), 1) if active else None},
    }
