"""AACSB assurance of learning (2020 Standard 5): one report per program, assembled from what CometIQ already holds.

For each program competency goal:
  1. Where it is taught: the curriculum map (introduced / practiced / mastered per course), with verified evidence.
  2. Direct measures available: graded assignments and rubric criteria (from Canvas) in program courses that practice
     the goal's skills, with their share of the course grade.
  3. Results: faculty-entered assessment results per term (students assessed, % meeting expectations vs. target).
  4. Closing the loop: actions recorded with results, faculty decisions on gaps in these skills, curriculum proposals
     adopted for these courses, and implemented changes.
Plus industry alignment (scorecard coverage for the program) and a status per goal.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (AssessmentResult, CourseAssignment, CurriculumProposal, GapDecision, Program, ProgramGoal, Skill, Syllabus)
from . import curriculum_map as cmap
from . import gap as gapsvc
from . import versions as vs

LEVEL_NAME = {"I": "Introduced", "P": "Practiced", "M": "Mastered"}


def goal_out(g: ProgramGoal, names: dict[int, str]) -> dict:
    return {"id": g.id, "code": g.code, "title": g.title, "description": g.description, "target_pct": g.target_pct,
            "skills": [{"id": sid, "name": names.get(sid, f"#{sid}")} for sid in (g.skill_ids or [])]}


def result_out(r: AssessmentResult) -> dict:
    pct = round(100 * r.students_meeting / r.students_assessed, 1) if r.students_assessed else None
    return {"id": r.id, "goal_id": r.goal_id, "term": r.term, "course_code": r.course_code, "measure": r.measure, "measure_type": r.measure_type,
            "students_assessed": r.students_assessed, "students_meeting": r.students_meeting, "met_pct": pct, "target_pct": r.target_pct,
            "met_target": pct is not None and pct >= r.target_pct, "notes": r.notes, "action": r.action,
            "entered_by": r.entered_by_name, "created_at": r.created_at}


def suggest_goals(db: Session, program: Program, target: str = gapsvc.ALL) -> list[dict]:
    """Starting points: the program's in-demand skills grouped by area. Faculty rename and edit them."""
    m = cmap.build(db, program, target)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for s in m["skills"]:
        if s["in_market"]:
            by_cat[s["category"]].append(s)
    out = []
    for cat, skills in sorted(by_cat.items(), key=lambda kv: -sum(x["demand"] or 0 for x in kv[1])):
        out.append({"title": f"Graduates apply {cat.lower()} to business problems",
                    "skills": [{"id": s["id"], "name": s["name"]} for s in sorted(skills, key=lambda x: -(x["demand"] or 0))][:6]})
    return out[:6]


def _status(goal: dict) -> tuple[str, str]:
    """Assessment results decide; without results, the curriculum map says whether the goal is taught at all."""
    results = goal["results"]
    taught = bool(goal["coverage"]["mastered_in"] or goal["coverage"]["practiced_in"])
    if not results:
        return ("not_assessed", "Taught but not yet assessed") if taught else ("gap", "No course practices these skills yet")
    latest_term = results[0]["term"]
    latest = [r for r in results if r["term"] == latest_term]
    if all(r["met_target"] for r in latest):
        return "met", f"Met the target in {latest_term}"
    if all(r["action"] for r in latest if not r["met_target"]):
        return "below_with_action", f"Below target in {latest_term}; action recorded"
    return "below", f"Below target in {latest_term}; no action recorded yet"


def report(db: Session, program: Program, target: str = gapsvc.ALL) -> dict:
    from .path import term_key
    from .scorecard import build as scorecard

    goals = list(db.scalars(select(ProgramGoal).where(ProgramGoal.program_id == program.id).order_by(ProgramGoal.code)))
    all_ids = {int(sid) for g in goals for sid in (g.skill_ids or [])}
    m = cmap.build(db, program, target, extra_skill_ids=sorted(all_ids))
    names = dict(db.execute(select(Skill.id, Skill.name).where(Skill.id.in_(all_ids))).all()) if all_ids else {}
    courses = {c["id"]: c for c in m["courses"]}
    codes = {c["code"] for c in m["courses"]}

    # graded work in program courses (latest syllabus per course with assignments)
    syl_by_course: dict[str, Syllabus] = {}
    for syl in db.scalars(select(Syllabus).where(Syllabus.org_id == program.org_id, Syllabus.course_id.in_(list(courses)))
                          .order_by(Syllabus.created_at.desc())):
        syl_by_course.setdefault(syl.course_id, syl)
    measures: dict[str, list[dict]] = defaultdict(list)   # skill name → graded measures
    for cid, syl in syl_by_course.items():
        rows = list(db.scalars(select(CourseAssignment).where(CourseAssignment.syllabus_id == syl.id)))
        if not rows:
            continue
        weights = vs.graded_weights([{"name": a.name, "points": a.points, "graded": a.graded, "skills": a.skills or [], "rubric": a.rubric or []}
                                     for a in rows])
        for a in rows:
            if not a.graded:
                continue
            for skill in a.skills or []:
                crit = [c["criterion"] for c in (a.rubric or []) if skill.lower() in f"{c.get('criterion', '')} {c.get('detail', '')}".lower()]
                measures[skill].append({"course": courses[cid]["code"], "assignment": a.name, "points": a.points,
                                        "rubric_criteria": crit, "course_grade_share": (weights.get(skill) or {}).get("share")})

    results = defaultdict(list)
    for r in db.scalars(select(AssessmentResult).where(AssessmentResult.goal_id.in_([g.id for g in goals]))):
        results[r.goal_id].append(result_out(r))
    decisions = list(db.scalars(select(GapDecision).join(Syllabus, Syllabus.id == GapDecision.syllabus_id).where(
        Syllabus.org_id == program.org_id, Syllabus.course_id.in_(list(courses)), GapDecision.status != "superseded")))
    proposals = list(db.scalars(select(CurriculumProposal).join(Syllabus, Syllabus.id == CurriculumProposal.syllabus_id).where(
        Syllabus.org_id == program.org_id, Syllabus.course_id.in_(list(courses)), CurriculumProposal.status.in_(("approved", "adopted")))))
    syl_code = {s.id: s.code for s in syl_by_course.values()}
    syl_code |= dict(db.execute(select(Syllabus.id, Syllabus.code).where(Syllabus.id.in_({d.syllabus_id for d in decisions} | {p.syllabus_id for p in proposals}))).all()) \
        if decisions or proposals else {}

    out_goals = []
    for g in goals:
        sids = [int(x) for x in (g.skill_ids or [])]
        cov = {"introduced_in": set(), "practiced_in": set(), "mastered_in": set(), "verified_in": set()}
        per_skill = []
        for sid in sids:
            sm = m["summary"].get(str(sid)) or {"introduced_in": [], "practiced_in": [], "mastered_in": [], "verified_in": []}
            for k in cov:
                cov[k] |= set(sm.get(k, []))
            per_skill.append({"skill": names.get(sid, f"#{sid}"), "introduced_in": sm["introduced_in"], "practiced_in": sm["practiced_in"],
                              "mastered_in": sm["mastered_in"], "measures": measures.get(names.get(sid, ""), [])})
        gres = sorted(results[g.id], key=lambda r: (term_key(r["term"]) or (0, 0)), reverse=True)
        skill_names = {names.get(sid) for sid in sids}
        loop = [{"kind": "decision", "course": syl_code.get(d.syllabus_id), "skill": d.skill.name if d.skill else None,
                 "decision": d.decision, "status": d.status, "rationale": d.rationale, "date": d.decided_at}
                for d in decisions if d.skill and d.skill.name in skill_names]
        loop += [{"kind": "proposal", "course": syl_code.get(p.syllabus_id), "title": f"#{p.number} {p.title}", "status": p.status,
                  "effective_term": p.effective_term, "date": p.decided_at}
                 for p in proposals if any(n and n.lower() in f"{p.title} {p.summary}".lower() for n in skill_names)]
        loop += [{"kind": "assessment action", "course": r["course_code"], "term": r["term"], "action": r["action"]} for r in gres if r["action"]]
        goal = {**goal_out(g, names), "coverage": {k: sorted(v & codes) for k, v in cov.items()}, "skills_detail": per_skill,
                "direct_measures": sum(len(x["measures"]) for x in per_skill), "results": gres, "closing_the_loop": loop}
        goal["status"], goal["status_text"] = _status(goal)
        goal["warnings"] = ([] if goal["coverage"]["practiced_in"] or goal["coverage"]["mastered_in"]
                            else ["The curriculum map shows no course practicing these skills"]) + \
                           ([] if goal["coverage"]["mastered_in"] else ["No course takes these skills to mastery"])
        out_goals.append(goal)

    sc = next((p for p in scorecard(db, program.org_id, target)["programs"] if p.get("id") == program.id), None)
    counts = defaultdict(int)
    for g in out_goals:
        counts[g["status"]] += 1
    terms = sorted({r["term"] for g in out_goals for r in g["results"]}, key=lambda t: term_key(t) or (0, 0))
    return {"program": {"id": program.id, "name": program.name, "catalog_year": program.catalog_year}, "target": target,
            "job_count": m["job_count"], "courses": len(m["courses"]),
            "courses_with_syllabus": m["totals"]["courses_with_syllabus"], "goals": out_goals,
            "summary": {"goals": len(out_goals), **{k: counts[k] for k in ("met", "below_with_action", "below", "not_assessed", "gap")},
                        "terms_assessed": terms, "direct_measures": sum(g["direct_measures"] for g in out_goals),
                        "industry_coverage": sc.get("coverage") if sc else None}}
