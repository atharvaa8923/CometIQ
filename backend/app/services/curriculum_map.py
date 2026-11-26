"""AACSB-style curriculum map: for each program skill, which courses Introduce (I), Practice (P) or Master (M) it.

Each cell says where its level came from, most trusted first:
  faculty map entry      set explicitly by faculty for this program
  faculty review         CometGap review of the course's latest syllabus: practiced → P, mentioned only → I
  syllabus signal        unreviewed keyword mentions: ≥2 mentions → P, 1 → I (marked unverified)
  catalog                the catalog description mentions the skill → I (unverified)
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Course, CourseSkill, CurriculumMapEntry, GapAnalysis, GapReview, Program, Skill, SkillBadge, Syllabus,
                      SyllabusVersion)
from . import gap as gapsvc

LEVELS = {"I": "Introduced", "P": "Practiced", "M": "Mastered", "-": "Not addressed"}
RANK = {"-": 0, "I": 1, "P": 2, "M": 3}


def program_courses(program: Program) -> list[tuple[Course, bool]]:
    """(course, is_core) for every course in the program: core first, then concentration courses (loaded in bulk)."""
    from sqlalchemy.orm import object_session

    db = object_session(program)
    core_ids = [pc.course_id for pc in program.core]
    conc_ids = [cc.course_id for conc in program.concentrations for cc in conc.courses]
    found = {c.id: c for c in db.scalars(select(Course).where(Course.id.in_(set(core_ids) | set(conc_ids))))}
    seen, out = set(), []
    for cid in sorted(core_ids, key=lambda i: found[i].code if i in found else ""):
        if cid in found and cid not in seen:
            seen.add(cid)
            out.append((found[cid], True))
    for cid in sorted(conc_ids, key=lambda i: found[i].code if i in found else ""):
        if cid in found and cid not in seen:
            seen.add(cid)
            out.append((found[cid], False))
    return out


def program_course_map(db: Session, org_id: str) -> dict[str, list[tuple[str, bool]]]:
    """{program_id: [(course_id, is_core), ...]} for every program of the organization, in two queries."""
    from ..models import Concentration, ConcentrationCourse, ProgramCore

    out: dict[str, dict[str, bool]] = {}
    for pid, cid in db.execute(select(ProgramCore.program_id, ProgramCore.course_id).join(Program, Program.id == ProgramCore.program_id)
                               .where(Program.org_id == org_id)):
        out.setdefault(pid, {})[cid] = True
    for pid, cid in db.execute(select(Concentration.program_id, ConcentrationCourse.course_id)
                               .join(Concentration, Concentration.id == ConcentrationCourse.concentration_id)
                               .join(Program, Program.id == Concentration.program_id).where(Program.org_id == org_id)):
        out.setdefault(pid, {}).setdefault(cid, False)
    return {pid: list(d.items()) for pid, d in out.items()}


def evidence_for_courses(db: Session, org_id: str, courses: list[Course]) -> dict[str, dict]:
    """Levels from each course's latest analyzed syllabus, for many courses in a constant number of queries:
    {course_id: {skill_id: (level, source, detail, unverified)}}."""
    if not courses:
        return {}
    by_id = {c.id: c for c in courses}
    by_code = {c.code.upper(): c.id for c in courses}
    rows = db.execute(select(Syllabus.id, Syllabus.course_id, Syllabus.code, GapAnalysis.id, GapAnalysis.syllabus_version_id, GapAnalysis.created_at)
                      .join(GapAnalysis, GapAnalysis.syllabus_id == Syllabus.id)
                      .where(Syllabus.org_id == org_id, (Syllabus.course_id.in_(list(by_id))) | (func.upper(Syllabus.code).in_(list(by_code))))).all()
    latest: dict[str, tuple] = {}
    for sid_, cid, code, ga_id, sv_id, at in rows:
        course_id = cid if cid in by_id else by_code.get((code or "").upper())
        if course_id and (course_id not in latest or at > latest[course_id][3]):
            latest[course_id] = (sid_, ga_id, sv_id, at)
    if not latest:
        return {}
    versions = {v.id: v for v in db.scalars(select(SyllabusVersion).where(SyllabusVersion.id.in_([x[2] for x in latest.values() if x[2]])))}
    legacy = [x[0] for x in latest.values() if not x[2]]
    legacy_skills: dict[str, dict] = {}
    if legacy:
        from ..models import SyllabusSkill

        for syl_id, name, mentions in db.execute(select(SyllabusSkill.syllabus_id, Skill.name, SyllabusSkill.mentions)
                                                 .join(Skill, Skill.id == SyllabusSkill.skill_id).where(SyllabusSkill.syllabus_id.in_(legacy))):
            legacy_skills.setdefault(syl_id, {})[name] = {"mentions": mentions}
    ids = dict(db.execute(select(Skill.name, Skill.id)).all())
    from ..models import User

    reviews: dict[str, list] = {}
    for rv, who in db.execute(select(GapReview, User.full_name).outerjoin(User, User.id == GapReview.reviewer_id)
                              .where(GapReview.analysis_id.in_([x[1] for x in latest.values()]))):
        reviews.setdefault(rv.analysis_id, []).append((rv, who))
    out: dict[str, dict] = {}
    for course_id, (syl_id, ga_id, sv_id, _) in latest.items():
        sv = versions.get(sv_id)
        skills = sv.skills if sv else legacy_skills.get(syl_id, {})
        label = (f"syllabus v{sv.version}" + (f" ({sv.semester})" if sv.semester else "")) if sv else "syllabus"
        ev: dict[int, tuple] = {}
        for name, info in skills.items():
            if name in ids:
                ev[ids[name]] = ("P" if info["mentions"] >= 2 else "I", "syllabus signal", f"{info['mentions']} mention(s) in {label}; not yet reviewed", True)
        for rv, who in reviews.get(ga_id, []):
            lvl = {"practiced": "P", "mentioned_only": "I"}.get(rv.faculty_status, "-")
            ev[rv.skill_id] = (lvl, "faculty review", f"{rv.faculty_status.replace('_', ' ')} — reviewed by {who or 'faculty'} on {label}"
                               + (f": {rv.rationale}" if rv.rationale else ""), False)
        out[course_id] = ev
    return out


def latest_syllabus_evidence(db: Session, org_id: str, course: Course) -> dict:
    """Levels from the latest analyzed syllabus of one course (see evidence_for_courses)."""
    return evidence_for_courses(db, org_id, [course]).get(course.id, {})


def build(db: Session, program: Program, target: str = gapsvc.ALL, top_n: int = 20,
          demand: tuple[list[dict], int] | None = None) -> dict:
    org = program.org_id
    courses = program_courses(program)
    demand, n_jobs = demand if demand is not None else gapsvc.market_demand(db, target, org)
    market = {d["skill_id"]: d for d in demand[:top_n]}
    entries = list(db.scalars(select(CurriculumMapEntry).where(CurriculumMapEntry.program_id == program.id)))
    skill_ids = list(market) + [e.skill_id for e in entries if e.skill_id not in market]
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.id.in_(skill_ids)))} if skill_ids else {}
    by_entry = {(e.course_id, e.skill_id): e for e in entries}
    badge_counts = dict(db.execute(select(SkillBadge.skill_id, func.count(func.distinct(SkillBadge.student_id)))
                                   .where(SkillBadge.org_id == org, SkillBadge.status == "active", SkillBadge.skill_id.in_(skill_ids))
                                   .group_by(SkillBadge.skill_id)).all()) if skill_ids else {}
    cells: dict[str, dict] = {}
    course_rows = []
    all_ev = evidence_for_courses(db, org, [c for c, _ in courses])
    all_cat: dict[str, set[int]] = {}
    for cid, sid in db.execute(select(CourseSkill.course_id, CourseSkill.skill_id).where(
            CourseSkill.course_id.in_([c.id for c, _ in courses]), CourseSkill.weight >= 1.0)):
        all_cat.setdefault(cid, set()).add(sid)
    for c, is_core in courses:
        syl_ev = all_ev.get(c.id, {})
        cat = all_cat.get(c.id, set())
        row = {}
        for sid in skill_ids:
            e = by_entry.get((c.id, sid))
            if e:
                row[str(sid)] = {"level": e.level, "source": "faculty map", "unverified": False,
                                 "detail": f"Set by {e.set_by_name or 'faculty'}" + (f": {e.rationale}" if e.rationale else "")}
            elif sid in syl_ev:
                lvl, src, det, unv = syl_ev[sid]
                row[str(sid)] = {"level": lvl, "source": src, "unverified": unv, "detail": det}
            elif sid in cat:
                row[str(sid)] = {"level": "I", "source": "catalog", "unverified": True, "detail": "Named in the catalog description"}
        cells[c.id] = row
        course_rows.append({"id": c.id, "code": c.code, "title": c.title, "is_core": is_core,
                            "has_syllabus": bool(syl_ev)})
    summary = {}
    for sid in skill_ids:
        lv = {lvl: [c["code"] for c in course_rows if cells[c["id"]].get(str(sid), {}).get("level") == lvl] for lvl in ("I", "P", "M")}
        verified = [c["code"] for c in course_rows if (x := cells[c["id"]].get(str(sid))) and not x["unverified"] and x["level"] in ("P", "M")]
        flags = []
        if not lv["P"] and not lv["M"]:
            flags.append("not practiced in any course")
        elif not lv["M"]:
            flags.append("no course takes it to mastery")
        if len(lv["P"]) + len(lv["M"]) >= 3:
            flags.append("practiced in 3+ courses: possible overlap")
        if (lv["P"] or lv["M"]) and not verified:
            flags.append("only unverified evidence")
        summary[str(sid)] = {"introduced_in": lv["I"], "practiced_in": lv["P"], "mastered_in": lv["M"], "verified_in": verified,
                             "flags": flags, "badge_holders": badge_counts.get(sid, 0)}
    skill_rows = [{"id": sid, "name": skills[sid].name, "category": skills[sid].category,
                   "demand": market[sid]["demand"] if sid in market else None, "in_market": sid in market} for sid in skill_ids if sid in skills]
    reached = sum(1 for s in skill_rows if summary[str(s["id"])]["practiced_in"] or summary[str(s["id"])]["mastered_in"])
    mastered = sum(1 for s in skill_rows if summary[str(s["id"])]["mastered_in"])
    return {"program": {"id": program.id, "name": program.name, "catalog_year": program.catalog_year}, "target": target, "job_count": n_jobs,
            "courses": course_rows, "skills": skill_rows, "cells": cells, "summary": summary, "levels": LEVELS,
            "totals": {"skills": len(skill_rows), "practiced_somewhere": reached, "mastered_somewhere": mastered,
                       "courses_with_syllabus": sum(c["has_syllabus"] for c in course_rows)}}


def to_xlsx(m: dict) -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Curriculum map"
    ws.append([f"{m['program']['name']} — curriculum map (I = introduced, P = practiced, M = mastered; * = unverified)"])
    ws.append([f"Catalog year {m['program'].get('catalog_year') or 'n/a'} · skills: top demand for {m['target']} ({m['job_count']} postings) + faculty entries"])
    ws.append([])
    ws.append(["Skill", "Category", "Share of postings"] + [c["code"] for c in m["courses"]] + ["Flags", "Students with verified badge"])
    for c in ws[4]:
        c.font = Font(bold=True)
    fill = {"I": "FEF3C7", "P": "D1ECDF", "M": "A7D7C5"}
    for s in m["skills"]:
        row = [s["name"], s["category"], f"{round(s['demand'] * 100)}%" if s["demand"] is not None else "—"]
        for c in m["courses"]:
            x = m["cells"][c["id"]].get(str(s["id"]))
            row.append("" if not x or x["level"] == "-" else x["level"] + ("*" if x["unverified"] else ""))
        sm = m["summary"][str(s["id"])]
        row += ["; ".join(sm["flags"]), sm["badge_holders"]]
        ws.append(row)
        for i, c in enumerate(m["courses"]):
            cell = ws.cell(row=ws.max_row, column=4 + i)
            v = (cell.value or "").rstrip("*")
            if v in fill:
                cell.fill = PatternFill("solid", fgColor=fill[v])
            cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 30
    det = wb.create_sheet("Evidence")
    det.append(["Course", "Skill", "Level", "Source", "Unverified", "Detail"])
    names = {s["id"]: s["name"] for s in m["skills"]}
    for c in m["courses"]:
        for sid, x in m["cells"][c["id"]].items():
            det.append([c["code"], names.get(int(sid)), x["level"], x["source"], "yes" if x["unverified"] else "", x["detail"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
