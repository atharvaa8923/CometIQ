"""Skill stacks: role-ready credentials built from faculty-verified badges.

A stack lists skills with a minimum level (practiced or mastered). A student completes it when they hold an active badge
for every skill at that level. For missing skills the student sees the courses where faculty confirmed the skill is taught,
preferring courses in their own program they have not taken yet. Employers can subscribe to a stack and are notified
when a student who is open to matching completes it.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import savepoint
from ..models import Course, Skill, SkillBadge, SkillStack, StackCompletion, StackSubscription, StudentCourse, StudentProfile, User
from .badges import faculty_basis
from .curriculum_map import program_courses

DEFAULTS = [
    ("Data Analyst", "Data Analyst", "Query, analyze and visualize business data.",
     [("SQL", "practiced"), ("Excel", "practiced"), ("Tableau", "practiced"), ("Statistics", "practiced")]),
    ("Analytics Engineer", "Data Engineer", "Build reliable data pipelines and models for analytics.",
     [("SQL", "mastered"), ("Python", "practiced"), ("Data Warehousing", "practiced"), ("ETL / Data Pipelines", "practiced")]),
    ("Machine Learning Practitioner", "Data Scientist", "Build, evaluate and deploy predictive models.",
     [("Python", "practiced"), ("Statistics", "practiced"), ("Machine Learning", "practiced"), ("MLOps", "practiced")]),
]
RANK = {"practiced": 1, "mastered": 2}


def ensure_defaults(db: Session, org_id: str) -> None:
    if db.scalar(select(SkillStack.id).where(SkillStack.org_id == org_id).limit(1)):
        return
    ids = dict(db.execute(select(Skill.name, Skill.id)).all())
    for name, fam, desc, reqs in DEFAULTS:
        req = [{"skill_id": ids[n], "level": lvl} for n, lvl in reqs if n in ids]
        if req:
            db.add(SkillStack(org_id=org_id, name=name, role_family=fam, description=desc, requirements=req))
    db.flush()


def _held(db: Session, student_id: str) -> dict[int, dict]:
    """Best active badge per skill: {skill_id: {"level", "course"}}."""
    out: dict[int, dict] = {}
    for b in db.scalars(select(SkillBadge).where(SkillBadge.student_id == student_id, SkillBadge.status == "active")):
        cur = out.get(b.skill_id)
        if not cur or RANK[b.level] > RANK[cur["level"]]:
            out[b.skill_id] = {"level": b.level, "course": b.course_code}
    return out


def progress(db: Session, stack: SkillStack, student_id: str, basis: dict | None = None, held: dict | None = None) -> dict:
    held = held if held is not None else _held(db, student_id)
    basis = basis if basis is not None else faculty_basis(db, stack.org_id)
    names = {s.id: s.name for s in db.scalars(select(Skill).where(Skill.id.in_([r["skill_id"] for r in stack.requirements])))}
    prof = db.get(StudentProfile, student_id)
    from ..models import Program

    in_program = {c.id for c, _ in program_courses(db.get(Program, prof.program_id))} if prof and prof.program_id else set()
    taken = {sc.course_id: sc.status for sc in db.scalars(select(StudentCourse).where(StudentCourse.user_id == student_id))}
    courses = {c.id: c for c in db.scalars(select(Course).where(Course.org_id == stack.org_id))}
    items, done = [], 0
    for r in stack.requirements:
        h = held.get(r["skill_id"])
        ok = bool(h) and RANK[h["level"]] >= RANK[r["level"]]
        done += ok
        nxt = []
        if not ok:
            for cid, skills in basis.items():
                b = skills.get(r["skill_id"])
                if b and RANK[b["level"]] >= RANK[r["level"]] and taken.get(cid) != "completed" and cid in courses:
                    c = courses[cid]
                    nxt.append({"course_id": cid, "code": c.code, "title": c.title, "level": b["level"], "in_program": cid in in_program,
                                "status": taken.get(cid)})
            nxt.sort(key=lambda x: (not x["in_program"], x["status"] != "enrolled", x["status"] != "planned", x["code"]))
        items.append({"skill_id": r["skill_id"], "skill": names.get(r["skill_id"], "?"), "required_level": r["level"], "done": ok,
                      "held": h, "next_courses": nxt[:3]})
    return {"id": stack.id, "name": stack.name, "role_family": stack.role_family, "description": stack.description,
            "done": done, "total": len(stack.requirements), "complete": done == len(stack.requirements) and done > 0, "items": items}


def check_completions(db: Session, org_id: str, student_ids: set[str] | None = None) -> int:
    """Record newly completed stacks and notify the student and subscribed employers. Returns how many were completed."""
    from .notify import notify

    stacks = list(db.scalars(select(SkillStack).where(SkillStack.org_id == org_id, SkillStack.is_active)))
    if not stacks:
        return 0
    q = select(SkillBadge.student_id).where(SkillBadge.org_id == org_id, SkillBadge.status == "active").distinct()
    students = set(db.scalars(q)) if student_ids is None else set(student_ids)
    have = {(c.stack_id, c.student_id) for c in db.scalars(select(StackCompletion))}
    n = 0
    for sid in students:
        held = _held(db, sid)
        for st in stacks:
            if (st.id, sid) in have:
                continue
            if st.requirements and all((h := held.get(r["skill_id"])) and RANK[h["level"]] >= RANK[r["level"]] for r in st.requirements):
                have.add((st.id, sid))
                try:
                    with savepoint(db):   # completed concurrently by another request: keep theirs, notify once
                        db.add(StackCompletion(stack_id=st.id, student_id=sid))
                except IntegrityError:
                    continue
                n += 1
                stu = db.get(User, sid)
                if stu:
                    notify(db, stu, "stack.completed", f"You completed the {st.name} skill stack",
                           "Every skill in the stack is now faculty-verified. Employers following this stack can see it.", "/match")
                prof = db.get(StudentProfile, sid)
                if prof and prof.open_to_match:
                    for sub in db.scalars(select(StackSubscription).where(StackSubscription.stack_id == st.id)):
                        emp = db.get(User, sub.employer_id)
                        if emp and emp.is_active:
                            notify(db, emp, "stack.alert", f"A student completed {st.name}",
                                   f"{stu.full_name if stu else 'A student'} now holds every faculty-verified skill in {st.name}.", "/match")
    db.flush()
    return n
