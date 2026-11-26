"""Interactive knowledge-graph map: Jobs → Skills → Courses → Students.

Returns a bounded, layered graph (role families or jobs, top skills, courses teaching them, students)
for a scope. Student visibility follows each role's permissions.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..db import get_db
from ..models import Course, CourseSkill, Job, JobSkill, Program, Skill, StudentCourse, StudentProfile, User
from ..security import current_user
from ..services.gap import IMPORTANCE_W
from ..services.match import students_skills

router = APIRouter(prefix="/api/graph", tags=["knowledge-graph"])


def _visible_students(db: Session, user: User, program_id: str | None) -> tuple[list[tuple[User, StudentProfile]], str]:
    """(students, mode). mode: 'named' | 'self' | 'aggregate'."""
    q = (select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id)
         .where(User.org_id == user.org_id, User.role == "student", User.is_active))
    if program_id:
        q = q.where(StudentProfile.program_id == program_id)
    if user.role in ("admin", "advisor"):
        return list(db.execute(q.order_by(User.full_name).limit(40)).all()), "named"
    if user.role == "employer":
        return list(db.execute(q.where(StudentProfile.open_to_match).order_by(User.full_name).limit(40)).all()), "named"
    if user.role == "student":
        return list(db.execute(q.where(User.id == user.id)).all()), "self"
    return list(db.execute(q).all()), "aggregate"  # faculty: counts only, no names


@router.get("/map")
def graph_map(role_family: str = "", program_id: str = "", max_skills: int = 18, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    from ..services.cache import cached

    # what a user sees depends on their role (and, for students, on themselves)
    who = (user.role, user.id if user.role == "student" else "")
    return cached(db, user.org_id, ("graph", role_family, program_id, max_skills, *who),
                  lambda: _graph_map(role_family, program_id, max_skills, user, db))


def _graph_map(role_family: str, program_id: str, max_skills: int, user: User, db: Session):
    if role_family and role_family not in ROLE_FAMILIES:
        raise HTTPException(400, "Unknown role family")
    program = db.get(Program, program_id) if program_id else None
    if program_id and (not program or program.org_id != user.org_id):
        raise HTTPException(404, "Program not found")
    max_skills = max(6, min(max_skills, 30))
    visible = (Job.org_id == user.org_id) | Job.org_id.is_(None)

    # ── Layer 1: jobs (role families, or individual postings when one family is chosen) ──
    from sqlalchemy.orm import lazyload

    jq = select(Job).options(lazyload(Job.skills)).where(Job.is_open, visible)
    if role_family:
        jq = jq.where(Job.role_family == role_family)
    jobs = list(db.scalars(jq))
    if role_family:
        groups = {f"job:{j.id}": [j] for j in jobs[:25]}
        job_nodes = [{"id": f"job:{j.id}", "type": "job", "label": j.title, "sub": j.company or "", "ref": j.id} for j in jobs[:25]]
    else:
        by_fam: dict[str, list[Job]] = defaultdict(list)
        for j in jobs:
            if j.role_family:
                by_fam[j.role_family].append(j)
        groups = {f"role:{f}": js for f, js in by_fam.items()}
        job_nodes = [{"id": f"role:{f}", "type": "job", "label": f, "sub": f"{len(js)} postings", "ref": f}
                     for f, js in sorted(by_fam.items(), key=lambda kv: -len(kv[1]))]

    # ── Layer 2: skills by demand within scope ──
    job_ids = [j.id for js in groups.values() for j in js]
    demand: dict[int, float] = defaultdict(float)
    edges_js: dict[tuple[str, int], float] = defaultdict(float)
    if job_ids:
        owner = {j.id: gid for gid, js in groups.items() for j in js}
        for jid, sid, imp in db.execute(select(JobSkill.job_id, JobSkill.skill_id, JobSkill.importance).where(JobSkill.job_id.in_(job_ids))).all():
            w = IMPORTANCE_W.get(imp, 1.0)
            demand[sid] += w
            edges_js[(owner[jid], sid)] += w
    top = sorted(demand, key=lambda s: -demand[s])[:max_skills]
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.id.in_(top)))}
    n_jobs = max(len(job_ids), 1)
    skill_nodes = [{"id": f"skill:{sid}", "type": "skill", "label": skills[sid].name, "sub": f"{round(100 * demand[sid] / n_jobs)}% weighted demand",
                    "ref": sid, "emerging": skills[sid].is_emerging} for sid in top if sid in skills]

    # ── Layer 3: courses teaching those skills (program courses only when a program is chosen) ──
    cq = (select(CourseSkill.course_id, CourseSkill.skill_id, CourseSkill.weight).join(Course)
          .where(Course.org_id == user.org_id, CourseSkill.skill_id.in_(top), CourseSkill.weight >= 1.0))
    if program:
        pool = {pc.course_id for pc in program.core} | {cc.course_id for c in program.concentrations for cc in c.courses}
        cq = cq.where(CourseSkill.course_id.in_(pool))
    cs_rows = db.execute(cq).all()
    course_score: dict[str, float] = defaultdict(float)
    for cid, sid, w in cs_rows:
        course_score[cid] += demand[sid] * w
    top_courses = sorted(course_score, key=lambda c: -course_score[c])[:22]
    courses = {c.id: c for c in db.scalars(select(Course).where(Course.id.in_(top_courses)))}
    course_nodes = [{"id": f"course:{cid}", "type": "course", "label": courses[cid].code, "sub": courses[cid].title, "ref": cid}
                    for cid in top_courses if cid in courses]

    # ── Layer 4: students ──
    studs, mode = _visible_students(db, user, program_id or None)
    student_nodes, edges_ss, edges_cs = [], [], []
    top_set, course_set = set(top), set(top_courses)
    if mode == "aggregate":
        counts: dict[int, int] = defaultdict(int)
        all_sk = students_skills(db, [u.id for u, _ in studs])
        for u, _ in studs:
            for sid, v in all_sk.get(u.id, {}).items():
                if sid in top_set and v["level"] >= 0.5:
                    counts[sid] += 1
        if studs:
            student_nodes.append({"id": "students:all", "type": "student", "label": f"{len(studs)} students", "sub": "names hidden for faculty", "ref": None})
            edges_ss = [{"source": f"skill:{sid}", "target": "students:all", "weight": n, "label": f"{n} students"} for sid, n in counts.items()]
    else:
        ids = [u.id for u, _ in studs]
        taken = defaultdict(list)
        if ids:
            for uid, cid, st in db.execute(select(StudentCourse.user_id, StudentCourse.course_id, StudentCourse.status)
                                          .where(StudentCourse.user_id.in_(ids), StudentCourse.course_id.in_(course_set))).all():
                taken[uid].append((cid, st))
        all_sk = students_skills(db, ids)
        for u, prof in studs:
            sk = all_sk.get(u.id, {})
            have = [(sid, v["level"]) for sid, v in sk.items() if sid in top_set and v["level"] >= 0.5]
            if not have and not taken[u.id]:
                continue
            student_nodes.append({"id": f"student:{u.id}", "type": "student", "label": "You" if u.id == user.id else u.full_name,
                                  "sub": prof.career_goal or prof.headline or "", "ref": u.id})
            edges_ss += [{"source": f"skill:{sid}", "target": f"student:{u.id}", "weight": round(lvl, 2)} for sid, lvl in have]
            edges_cs += [{"source": f"course:{cid}", "target": f"student:{u.id}", "weight": 1, "label": st} for cid, st in taken[u.id]]

    edges = ([{"source": g, "target": f"skill:{sid}", "weight": round(w / max(len(groups.get(g, [])), 1), 2)}
              for (g, sid), w in edges_js.items() if sid in top_set]
             + [{"source": f"skill:{sid}", "target": f"course:{cid}", "weight": w} for cid, sid, w in cs_rows if cid in course_set]
             + edges_ss + edges_cs)
    return {"scope": {"role_family": role_family or None, "program": program.name if program else None, "jobs": len(job_ids)},
            "student_mode": mode, "nodes": job_nodes + skill_nodes + course_nodes + student_nodes, "edges": edges,
            "role_families": [f for f in ROLE_FAMILIES],
            "programs": [{"id": p.id, "name": p.name} for p in db.scalars(select(Program).where(Program.org_id == user.org_id).order_by(Program.name))],
            "counts": {"jobs": len(job_nodes), "skills": len(skill_nodes), "courses": len(course_nodes), "students": len(student_nodes)}}


@router.get("/skill/{sid}")
def skill_detail(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    visible = (Job.org_id == user.org_id) | Job.org_id.is_(None)
    total = db.scalar(select(func.count()).select_from(Job).where(Job.is_open, visible)) or 1
    jobs = db.execute(select(Job, JobSkill.importance).join(JobSkill).where(JobSkill.skill_id == sid, Job.is_open, visible)
                      .order_by(Job.posted_at.desc())).all()
    fam = defaultdict(int)
    for j, _ in jobs:
        fam[j.role_family or "Other"] += 1
    courses = db.execute(select(Course, CourseSkill.weight).join(CourseSkill).where(Course.org_id == user.org_id, CourseSkill.skill_id == sid)
                         .order_by(CourseSkill.weight.desc(), Course.code)).all()
    return {"id": s.id, "name": s.name, "category": s.category, "is_emerging": s.is_emerging,
            "job_count": len(jobs), "share": round(100 * len(jobs) / total, 1),
            "required_share": round(100 * sum(1 for _, imp in jobs if imp == "required") / max(len(jobs), 1), 1),
            "by_role": sorted(({"role": k, "jobs": v} for k, v in fam.items()), key=lambda x: -x["jobs"]),
            "sample_jobs": [{"id": j.id, "title": j.title, "company": j.company} for j, _ in jobs[:5]],
            "courses": [{"id": c.id, "code": c.code, "title": c.title, "primary": w >= 1} for c, w in courses[:12]]}
