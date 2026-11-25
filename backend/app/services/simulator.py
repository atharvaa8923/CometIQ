"""Program simulator: try a curriculum redesign on a copy of the program before proposing it.

Operations (applied in order, nothing is saved):
  set_level      {course_id, skill_id, level: I|P|M|-}
  move_skill     {skill_id, from_course, to_course, level?}   remove from one course, add to another
  add_course     {course_id, core?}                            add a catalog course to the program
  remove_course  {course_id}
  add_prereq     {course_id, requires_id}                      a new required prerequisite (AND)
  remove_prereq  {course_id, requires_id}

Results compare the program before and after: demand-weighted coverage (P/M = 1, I = 0.5), the I→P→M flags,
the longest prerequisite chain among core courses (minimum number of terms), and students' saved CometPath plans
that gain a problem (a planned course whose prerequisites are no longer met in time, or a planned core course that was
removed), become broken, or are fixed. Student results are aggregated; no student is named.
"""
import copy
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill, Program, StudentCourse, StudentProfile
from . import curriculum_map as cmap
from . import gap as gapsvc
from .path import load_graph, term_key

W = {"M": 1.0, "P": 1.0, "I": 0.5, "-": 0.0}
OPS = {"set_level", "move_skill", "add_course", "remove_course", "add_prereq", "remove_prereq"}


def _metrics(courses: dict[str, dict], cells: dict[str, dict[str, str]], skills: list[dict]) -> dict:
    per_skill = {}
    total = sum(s["demand"] or 0 for s in skills if s["in_market"]) or 1
    earned = 0.0
    for s in skills:
        sid = str(s["id"])
        lv = {lvl: sorted(courses[c]["code"] for c in courses if cells.get(c, {}).get(sid) == lvl) for lvl in ("I", "P", "M")}
        best = max((W[cells.get(c, {}).get(sid, "-")] for c in courses), default=0.0)
        if s["in_market"]:
            earned += (s["demand"] or 0) * best
        flags = []
        if not lv["P"] and not lv["M"]:
            flags.append("not practiced in any course")
        elif not lv["M"]:
            flags.append("no course takes it to mastery")
        if len(lv["P"]) + len(lv["M"]) >= 3:
            flags.append("practiced in 3+ courses")
        per_skill[sid] = {"levels": lv, "flags": flags}
    market = [s for s in skills if s["in_market"]]
    return {"coverage": round(100 * earned / total, 1), "per_skill": per_skill,
            "never_practiced": sum(1 for s in market if "not practiced in any course" in per_skill[str(s["id"])]["flags"]),
            "no_mastery": sum(1 for s in market if per_skill[str(s["id"])]["flags"][:1] in (["not practiced in any course"], ["no course takes it to mastery"])),
            "overlaps": sum(1 for s in market if "practiced in 3+ courses" in per_skill[str(s["id"])]["flags"]),
            "courses": len(courses)}


def _chain(prereqs: dict[str, dict[int, list[str]]], cid: str, memo: dict, stack: set) -> int:
    """Minimum number of terms to reach cid: 1 + max over AND groups of the cheapest OR option."""
    if cid in memo:
        return memo[cid]
    if cid in stack:
        raise HTTPException(400, "These prerequisite changes create a cycle")
    stack.add(cid)
    v = 1 + max((min(_chain(prereqs, o, memo, stack) for o in opts) for opts in prereqs.get(cid, {}).values() if opts), default=0)
    stack.discard(cid)
    memo[cid] = v
    return v


def _plan_issues(db: Session, program_id: str, prereqs: dict, removed: set[str], core_before: set[str], codes: dict[str, str]) -> dict[str, set[str]]:
    """For each student in the program with a saved plan: the set of problems in that plan under these prerequisites."""
    out: dict[str, set[str]] = {}
    for uid in db.scalars(select(StudentProfile.user_id).where(StudentProfile.program_id == program_id)):
        rows = list(db.scalars(select(StudentCourse).where(StudentCourse.user_id == uid)))
        planned = [r for r in rows if r.status == "planned"]
        if not planned:
            continue
        done = {r.course_id for r in rows if r.status in ("completed", "enrolled")}
        issues: set[str] = set()
        for r in planned:
            if r.course_id in removed and r.course_id in core_before:
                issues.add(f"{codes.get(r.course_id, '?')} is planned but no longer in the program")
                continue
            earlier = done | {p.course_id for p in planned if term_key(p.term) < term_key(r.term)}
            for opts in prereqs.get(r.course_id, {}).values():
                if opts and not any(o in earlier for o in opts):
                    issues.add(f"{codes.get(r.course_id, '?')} would need {' or '.join(codes.get(o, '?') for o in opts)} first")
        out[uid] = issues
    return out


def _plan_impact(before: dict[str, set[str]], after: dict[str, set[str]]) -> dict:
    reasons: dict[str, int] = defaultdict(int)
    affected = newly = fixed = 0
    for uid, a in after.items():
        b = before.get(uid, set())
        new = a - b
        for r in new:
            reasons[r] += 1
        affected += bool(new)
        newly += bool(a) and not b
        fixed += bool(b) and not a
    return {"students_with_saved_plans": len(after), "affected": affected, "newly_broken": newly, "fixed": fixed,
            "already_broken": sum(1 for v in before.values() if v),
            "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:10])}


def simulate(db: Session, program: Program, ops: list[dict], target: str = gapsvc.ALL) -> dict:
    base = cmap.build(db, program, target)
    skills = base["skills"]
    courses = {c["id"]: {"code": c["code"], "title": c["title"], "is_core": c["is_core"]} for c in base["courses"]}
    cells = {cid: {sid: x["level"] for sid, x in row.items()} for cid, row in base["cells"].items()}
    g = load_graph(db, program.org_id)
    prereqs = copy.deepcopy(g.prereqs)
    codes = {cid: c.code for cid, c in g.courses.items()}
    before = {"courses": copy.deepcopy(courses), "cells": copy.deepcopy(cells), "prereqs": copy.deepcopy(prereqs)}
    skill_ids = {str(s["id"]) for s in skills}
    applied, removed = [], set()
    for i, op in enumerate(ops):
        kind = op.get("op")
        if kind not in OPS:
            raise HTTPException(400, f"Operation {i + 1}: unknown operation")
        cid = op.get("course_id")
        if kind == "set_level":
            if cid not in courses or str(op.get("skill_id")) not in skill_ids or op.get("level") not in W:
                raise HTTPException(400, f"Operation {i + 1}: course, skill or level is not valid for this program")
            cells.setdefault(cid, {})[str(op["skill_id"])] = op["level"]
            applied.append(f"{courses[cid]['code']}: {next(s['name'] for s in skills if str(s['id']) == str(op['skill_id']))} → {op['level']}")
        elif kind == "move_skill":
            a, b, sid = op.get("from_course"), op.get("to_course"), str(op.get("skill_id"))
            if a not in courses or b not in courses or sid not in skill_ids or a == b:
                raise HTTPException(400, f"Operation {i + 1}: choose a skill and two different program courses")
            lvl = op.get("level") or cells.get(a, {}).get(sid) or "P"
            if lvl == "-":
                lvl = "P"
            cells.setdefault(a, {})[sid] = "-"
            cells.setdefault(b, {})[sid] = lvl
            applied.append(f"Move {next(s['name'] for s in skills if str(s['id']) == sid)} from {courses[a]['code']} to {courses[b]['code']} ({lvl})")
        elif kind == "add_course":
            c = db.get(Course, cid)
            if not c or c.org_id != program.org_id or cid in courses:
                raise HTTPException(400, f"Operation {i + 1}: pick a catalog course that is not already in the program")
            courses[cid] = {"code": c.code, "title": c.title, "is_core": bool(op.get("core"))}
            ev = cmap.latest_syllabus_evidence(db, program.org_id, c)
            cat = {cs.skill_id for cs in db.scalars(select(CourseSkill).where(CourseSkill.course_id == c.id, CourseSkill.weight >= 1.0))}
            cells[cid] = {sid: (ev[int(sid)][0] if int(sid) in ev else "I" if int(sid) in cat else "-") for sid in skill_ids}
            removed.discard(cid)
            applied.append(f"Add {c.code} as {'core' if op.get('core') else 'an elective'}")
        elif kind == "remove_course":
            if cid not in courses:
                raise HTTPException(400, f"Operation {i + 1}: that course is not in the program")
            applied.append(f"Remove {courses[cid]['code']}")
            courses.pop(cid)
            cells.pop(cid, None)
            removed.add(cid)
        else:
            req = op.get("requires_id")
            if cid not in g.courses or req not in g.courses or cid == req:
                raise HTTPException(400, f"Operation {i + 1}: choose two different catalog courses")
            groups = prereqs.setdefault(cid, {})
            if kind == "add_prereq":
                if any(groups.get(k) == [req] for k in groups):
                    raise HTTPException(400, f"Operation {i + 1}: {codes[cid]} already requires {codes[req]}")
                groups[max(groups, default=-1) + 1] = [req]
                applied.append(f"{codes[cid]} now requires {codes[req]}")
            else:
                found = False
                for k in list(groups):
                    if req in groups[k]:
                        groups[k] = [o for o in groups[k] if o != req]
                        found = True
                        if not groups[k]:
                            groups.pop(k)
                if not found:
                    raise HTTPException(400, f"Operation {i + 1}: {codes[cid]} does not require {codes[req]}")
                applied.append(f"{codes[cid]} no longer requires {codes[req]}")
    mb, ma = _metrics(before["courses"], before["cells"], skills), _metrics(courses, cells, skills)
    core_b = [c for c, v in before["courses"].items() if v["is_core"]]
    core_a = [c for c, v in courses.items() if v["is_core"]]
    chain_b = max((_chain(before["prereqs"], c, {}, set()) for c in core_b), default=0)
    memo: dict = {}
    chain_a = max((_chain(prereqs, c, memo, set()) for c in core_a), default=0)
    longest = sorted(((codes.get(c, "?"), memo.get(c, 0)) for c in core_a), key=lambda x: -x[1])[:5]
    issues_b = _plan_issues(db, program.id, before["prereqs"], set(), set(core_b), codes)
    issues_a = _plan_issues(db, program.id, prereqs, removed, set(core_b), codes)
    br_b, br_a = sum(1 for v in issues_b.values() if v), sum(1 for v in issues_a.values() if v)
    changes = []
    for s in skills:
        sid = str(s["id"])
        pb, pa = mb["per_skill"][sid], ma["per_skill"][sid]
        if pb != pa:
            changes.append({"skill": s["name"], "share": round((s["demand"] or 0) * 100), "before": pb, "after": pa})
    return {
        "program": base["program"], "target": target, "operations": applied,
        "before": {k: mb[k] for k in ("coverage", "never_practiced", "no_mastery", "overlaps", "courses")} | {"max_chain_terms": chain_b, "plans_broken": br_b},
        "after": {k: ma[k] for k in ("coverage", "never_practiced", "no_mastery", "overlaps", "courses")} | {"max_chain_terms": chain_a, "plans_broken": br_a},
        "plans": _plan_impact(issues_b, issues_a),
        "longest_chains": [{"course": c, "terms": t} for c, t in longest],
        "skill_changes": changes,
        "note": "Simulation only: nothing is saved. Coverage counts practiced or mastered as 1 and introduced as 0.5.",
    }
