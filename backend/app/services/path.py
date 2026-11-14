"""CometPath engine — degree progress, prerequisite logic, career-driven recommendations
and a semester-by-semester plan.

Prerequisite semantics (from the JSOM planner): edges of a course that share a `group`
are alternatives (OR); different groups must all be satisfied (AND).
Core semantics: or_group 0 = required course; or_group N > 0 = take any one course of group N.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CoursePrereq, CourseSkill, Program, StudentCourse, StudentProfile
from .gap import market_demand

TAKEN = ("completed", "enrolled")
SEASONS = ["Spring", "Summer", "Fall"]


@dataclass
class Graph:
    prereqs: dict[str, dict[int, list[str]]] = field(default_factory=dict)   # course -> group -> [options]
    dependents: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    courses: dict[str, Course] = field(default_factory=dict)
    skills: dict[str, dict[int, float]] = field(default_factory=lambda: defaultdict(dict))


def load_graph(db: Session, org_id: str) -> Graph:
    g = Graph()
    g.courses = {c.id: c for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    pre: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for e in db.scalars(select(CoursePrereq).join(Course, Course.id == CoursePrereq.course_id).where(Course.org_id == org_id)):
        pre[e.course_id][e.group].append(e.requires_id)
        g.dependents[e.requires_id].add(e.course_id)
    g.prereqs = {k: dict(v) for k, v in pre.items()}
    for cs in db.scalars(select(CourseSkill).join(Course).where(Course.org_id == org_id)):
        g.skills[cs.course_id][cs.skill_id] = cs.weight
    return g


def unmet_groups(g: Graph, cid: str, have: set[str]) -> list[list[str]]:
    return [opts for opts in g.prereqs.get(cid, {}).values() if not any(o in have for o in opts)]


def depth(g: Graph, cid: str, seen=None) -> int:
    """Longest chain of courses that depend on this one (schedule long chains first)."""
    seen = seen or set()
    if cid in seen:
        return 0
    seen.add(cid)
    return 1 + max((depth(g, d, seen) for d in g.dependents.get(cid, ())), default=0)


# ── terms ──────────────────────────────────────────────────────────────────────
def next_terms(start: str, n: int, summer: bool) -> list[str]:
    try:
        season, year = start.split()
        y, i = int(year), SEASONS.index(season)
    except (ValueError, IndexError):
        y, i = 2026, 2
    out = []
    while len(out) < n:
        s = SEASONS[i]
        if s != "Summer" or summer:
            out.append(f"{s} {y}")
        i += 1
        if i == 3:
            i, y = 0, y + 1
    return out


# ── career demand ──────────────────────────────────────────────────────────────
def career_vector(db: Session, goal: str | None, org_id: str) -> tuple[dict[int, dict], int]:
    if not goal:
        return {}, 0
    demand, n = market_demand(db, goal, org_id)
    return {d["skill_id"]: d for d in demand}, n


def career_score(g: Graph, cid: str, vec: dict[int, dict]) -> float:
    return round(sum(vec[s]["demand"] * w for s, w in g.skills.get(cid, {}).items() if s in vec), 4)


def top_skills(g: Graph, cid: str, vec: dict[int, dict], k: int = 3) -> list[str]:
    hits = sorted(((vec[s]["demand"] * w, vec[s]["name"]) for s, w in g.skills.get(cid, {}).items() if s in vec), reverse=True)
    return [n for _, n in hits[:k]]


# ── progress ───────────────────────────────────────────────────────────────────
def core_slots(program: Program) -> list[dict]:
    slots: dict[str, dict] = {}
    for pc in program.core:
        key = f"or{pc.or_group}" if pc.or_group else f"req{pc.course_id}"
        slots.setdefault(key, {"key": key, "or_group": pc.or_group, "options": []})["options"].append(pc.course_id)
    return list(slots.values())


def student_state(db: Session, user_id: str) -> tuple[StudentProfile | None, dict[str, StudentCourse]]:
    prof = db.get(StudentProfile, user_id)
    rows = {sc.course_id: sc for sc in db.scalars(select(StudentCourse).where(StudentCourse.user_id == user_id))}
    return prof, rows


def progress(db: Session, prof: StudentProfile, rows: dict[str, StudentCourse], g: Graph) -> dict:
    program = db.get(Program, prof.program_id) if prof.program_id else None
    if not program:
        return {"program": None}
    status_of = {cid: sc.status for cid, sc in rows.items()}
    cred = lambda cid: g.courses[cid].credits if cid in g.courses else 3  # noqa: E731
    slots = []
    core_ids: set[str] = set()
    for s in core_slots(program):
        core_ids.update(s["options"])
        best = next((st for st in ("completed", "enrolled", "planned") for o in s["options"] if status_of.get(o) == st), None)
        slots.append({"or_group": s["or_group"], "status": best or "remaining",
                      "options": [{"id": o, "code": g.courses[o].code, "title": g.courses[o].title, "status": status_of.get(o)} for o in s["options"]]})
    conc = next((c for c in program.concentrations if c.id == prof.concentration_id), None)
    conc_ids = {cc.course_id for cc in conc.courses} if conc else set()
    sch = {st: sum(cred(cid) for cid, s in status_of.items() if s == st) for st in ("completed", "enrolled", "planned")}
    conc_sch = {st: sum(cred(cid) for cid, s in status_of.items() if s == st and cid in conc_ids and cid not in core_ids)
                for st in ("completed", "enrolled", "planned")}
    total = program.total_sch or 36
    return {
        "program": {"id": program.id, "name": program.name, "type": program.type, "total_sch": total, "is_stem": program.is_stem,
                    "catalog_url": program.catalog_url, "prereq_notes": program.prereq_notes},
        "concentration": {"id": conc.id, "name": conc.name, "required_sch": conc.required_sch} if conc else None,
        "sch": sch, "total_sch": total,
        "percent_complete": round(100 * sch["completed"] / total, 1),
        "percent_with_plan": round(100 * min(total, sum(sch.values())) / total, 1),
        "core": {"slots": slots, "done": sum(s["status"] in TAKEN for s in slots), "planned": sum(s["status"] == "planned" for s in slots), "total": len(slots)},
        "concentration_sch": conc_sch,
    }


# ── recommendations ────────────────────────────────────────────────────────────
def program_pool(program: Program, conc_id: str | None) -> tuple[set[str], set[str]]:
    core = {pc.course_id for pc in program.core}
    conc = next((c for c in program.concentrations if c.id == conc_id), None)
    pool = {cc.course_id for cc in conc.courses} if conc else {cc.course_id for c in program.concentrations for cc in c.courses}
    return core, pool - core


def recommendations(db: Session, prof: StudentProfile, rows: dict[str, StudentCourse], g: Graph, org_id: str, limit: int = 12) -> dict:
    program = db.get(Program, prof.program_id) if prof.program_id else None
    if not program:
        return {"eligible": [], "blocked": []}
    vec, n = career_vector(db, prof.career_goal, org_id)
    have = {cid for cid, sc in rows.items() if sc.status in TAKEN}
    taken_any = set(rows)
    core, electives = program_pool(program, prof.concentration_id)
    slots = core_slots(program)
    satisfied_groups = {s["or_group"] for s in slots if s["or_group"] and any(o in taken_any for o in s["options"])}
    eligible, blocked = [], []
    for cid in (core | electives) - taken_any:
        if cid not in g.courses:
            continue
        pc_group = next((s["or_group"] for s in slots if cid in s["options"] and s["or_group"]), 0)
        if pc_group in satisfied_groups:
            continue  # alternative already chosen for this core slot
        c = g.courses[cid]
        score = career_score(g, cid, vec)
        reasons = []
        if cid in core:
            reasons.append("Core requirement" if not pc_group else f"Core (choose one of group {pc_group})")
        sk = top_skills(g, cid, vec)
        if sk:
            reasons.append(f"Builds {', '.join(sk)} for {prof.career_goal}")
        unlocks = [g.courses[d].code for d in g.dependents.get(cid, ()) if d in core | electives][:3]
        if unlocks:
            reasons.append(f"Unlocks {', '.join(unlocks)}")
        item = {"id": cid, "code": c.code, "title": c.title, "credits": c.credits, "is_core": cid in core,
                "career_score": score, "reasons": reasons, "skills": sk}
        missing = unmet_groups(g, cid, have)
        if missing:
            item["missing_prereqs"] = [" or ".join(g.courses[o].code for o in grp if o in g.courses) for grp in missing]
            blocked.append(item)
        else:
            eligible.append(item)
    key = lambda x: (not x["is_core"], -x["career_score"], x["code"])  # noqa: E731
    eligible.sort(key=key)
    blocked.sort(key=key)
    return {"career_goal": prof.career_goal, "job_count": n, "eligible": eligible[:limit], "blocked": blocked[:limit]}


# ── plan generation ────────────────────────────────────────────────────────────
def generate_plan(db: Session, prof: StudentProfile, rows: dict[str, StudentCourse], g: Graph, org_id: str) -> dict:
    program = db.get(Program, prof.program_id) if prof.program_id else None
    if not program:
        return {"terms": [], "warnings": ["Choose a program first."]}
    vec, n_jobs = career_vector(db, prof.career_goal, org_id)
    done = {cid for cid, sc in rows.items() if sc.status in TAKEN}
    cred = lambda cid: g.courses[cid].credits  # noqa: E731
    score = lambda cid: career_score(g, cid, vec)  # noqa: E731
    chosen: dict[str, str] = {}  # course -> reason
    warnings: list[str] = []

    # 1. unmet core slots (pick the best career-fit option in OR groups)
    for s in core_slots(program):
        if any(o in done for o in s["options"]):
            continue
        best = max(s["options"], key=lambda o: (score(o), -len(unmet_groups(g, o, done))))
        chosen[best] = "Core requirement" if not s["or_group"] else "Core (best career fit in its OR group)"

    # 2. electives up to total SCH, best career fit first
    core, electives = program_pool(program, prof.concentration_id)
    total_needed = (program.total_sch or 36) - sum(cred(c) for c in done if c in g.courses)
    planned_sch = sum(cred(c) for c in chosen)
    ranked = sorted((c for c in electives - done - set(chosen) if c in g.courses),
                    key=lambda c: (-score(c), len(unmet_groups(g, c, done)), g.courses[c].code))
    # pass 1: electives whose prerequisites are already met or planned; pass 2: anything (prereqs get added)
    for strict in (True, False):
        for cid in ranked:
            if planned_sch >= total_needed:
                break
            if cid in chosen or (strict and unmet_groups(g, cid, done | set(chosen))):
                continue
            sk = top_skills(g, cid, vec, 2)
            chosen[cid] = f"Elective — builds {', '.join(sk)}" if sk else "Concentration elective"
            planned_sch += cred(cid)

    # 3. prerequisite closure: add a missing prerequisite when no option is already in the plan
    for _ in range(5):
        added = False
        for cid in list(chosen):
            for grp in unmet_groups(g, cid, done | set(chosen)):
                opts = [o for o in grp if o in g.courses]
                if not opts:
                    continue
                pick = max(opts, key=lambda o: (o in core or o in electives, score(o)))
                chosen[pick] = f"Prerequisite for {g.courses[cid].code}"
                added = True
        if not added:
            break

    # 4. schedule into terms respecting prerequisites and credit load
    terms = next_terms(prof.start_term, 12, prof.include_summer)
    placed: dict[str, int] = {}
    remaining = set(chosen)
    plan_terms = []
    for ti, term in enumerate(terms):
        if not remaining:
            break
        cap = min(prof.credits_per_term, 6) if term.startswith("Summer") else prof.credits_per_term
        before = done | {c for c, t in placed.items() if t < ti}
        # a prerequisite group with no option in the plan or history is assumed waived (flagged in warnings)
        avail = [c for c in remaining if all(any(o in before for o in grp) or not any(o in chosen for o in grp)
                                             for grp in g.prereqs.get(c, {}).values())]
        avail.sort(key=lambda c: (c not in core, -depth(g, c), -score(c), g.courses[c].code))
        load, items = 0, []
        for c in avail:
            if load + cred(c) <= cap or (not items and cred(c) > cap):
                items.append(c)
                load += cred(c)
                placed[c] = ti
        remaining -= set(items)
        plan_terms.append({"term": term, "credits": load, "courses": [
            {"id": c, "code": g.courses[c].code, "title": g.courses[c].title, "credits": cred(c), "reason": chosen[c],
             "is_core": c in core, "skills": top_skills(g, c, vec, 3)} for c in sorted(items, key=lambda x: g.courses[x].code)]})
    if remaining:
        warnings.append(f"{len(remaining)} course(s) could not be scheduled within 12 terms — check prerequisites with your advisor.")
    for c in chosen:
        for grp in g.prereqs.get(c, {}).values():
            if not any(o in done or o in chosen for o in grp):
                warnings.append(f"{g.courses[c].code} lists a prerequisite outside your plan ({' or '.join(g.courses[o].code for o in grp if o in g.courses)}) "
                                "— it may be waived by prior coursework; confirm with your advisor.")
    if program.prereq_notes:
        warnings.append(f"Program prerequisites: {program.prereq_notes}")

    suggestion = best_concentration(program, prof.concentration_id, g, vec)
    readiness = career_readiness(g, done | set(chosen), done, vec, n_jobs, prof.career_goal)
    total_sch = sum(cred(c) for c in done) + sum(cred(c) for c in chosen)
    return {"terms": plan_terms, "graduation_term": plan_terms[-1]["term"] if plan_terms else None, "planned_sch": sum(cred(c) for c in chosen),
            "total_sch": total_sch, "required_sch": program.total_sch, "warnings": list(dict.fromkeys(warnings)), "readiness": readiness,
            "concentration_suggestion": suggestion}


def best_concentration(program: Program, current: str | None, g: Graph, vec: dict[int, dict]) -> dict | None:
    """Suggest the concentration whose top courses best match the career goal."""
    if not vec or len(program.concentrations) < 2:
        return None
    fit = {}
    for c in program.concentrations:
        scores = sorted((career_score(g, cc.course_id, vec) for cc in c.courses), reverse=True)[:5]
        fit[c.id] = (sum(scores), c.name)
    best_id = max(fit, key=lambda k: fit[k][0])
    cur = fit.get(current, (0.0, None))
    if best_id != current and fit[best_id][0] > max(cur[0] * 1.25, 0.1):
        return {"id": best_id, "name": fit[best_id][1], "current": cur[1],
                "reason": f"Its courses build more of the skills employers want ({fit[best_id][0]:.1f} vs {cur[0]:.1f} career-fit points)."}
    return None


def career_readiness(g: Graph, with_plan: set[str], done: set[str], vec: dict[int, dict], n_jobs: int, goal: str | None, top: int = 15) -> dict:
    if not vec:
        return {"goal": goal, "job_count": 0, "skills": [], "now": 0, "with_plan": 0}
    top_demand = sorted(vec.values(), key=lambda d: -d["demand"])[:top]
    level = lambda ids, sid: max((g.skills.get(c, {}).get(sid, 0) for c in ids), default=0)  # noqa: E731
    rows, tot, now, later = [], 0.0, 0.0, 0.0
    for d in top_demand:
        a, b = level(done, d["skill_id"]), level(with_plan, d["skill_id"])
        status = "have" if a >= 1 else "partial" if a > 0 else "planned" if b > 0 else "gap"
        teach = [g.courses[c].code for c, sk in g.skills.items() if sk.get(d["skill_id"], 0) >= 1 and c not in with_plan][:3]
        rows.append({"skill": d["name"], "category": d["category"], "demand": d["demand"], "status": status, "courses_outside_plan": teach})
        tot += d["demand"]
        now += d["demand"] * min(a, 1)
        later += d["demand"] * min(b, 1)
    return {"goal": goal, "job_count": n_jobs, "skills": rows,
            "now": round(100 * now / tot, 1) if tot else 0, "with_plan": round(100 * later / tot, 1) if tot else 0}
