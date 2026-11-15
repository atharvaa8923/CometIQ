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
    seen, out = set(), []
    for pc in sorted(program.core, key=lambda x: x.course.code):
        if pc.course.id not in seen:
            seen.add(pc.course.id)
            out.append((pc.course, True))
    for conc in program.concentrations:
        for cc in sorted(conc.courses, key=lambda x: x.course.code):
            if cc.course.id not in seen:
                seen.add(cc.course.id)
                out.append((cc.course, False))
    return out


def latest_syllabus_evidence(db: Session, org_id: str, course: Course) -> dict:
    """Levels from the latest analyzed syllabus of a course: {skill_id: (level, source, detail, unverified)}."""
    syl = db.scalar(select(Syllabus).where(Syllabus.org_id == org_id, (Syllabus.course_id == course.id) | (func.upper(Syllabus.code) == course.code.upper()))
                    .join(GapAnalysis, GapAnalysis.syllabus_id == Syllabus.id).order_by(GapAnalysis.created_at.desc()).limit(1))
    if not syl:
        return {}
    ga = syl.analyses[0]
    out: dict[int, tuple] = {}
    sv = db.get(SyllabusVersion, ga.syllabus_version_id) if ga.syllabus_version_id else None
    skills = sv.skills if sv else {ss.skill.name: {"mentions": ss.mentions} for ss in syl.skills}
    ids = dict(db.execute(select(Skill.name, Skill.id).where(Skill.name.in_(list(skills)))).all()) if skills else {}
    label = f"syllabus v{sv.version}" + (f" ({sv.semester})" if sv and sv.semester else "") if sv else "syllabus"
    for name, info in skills.items():
        if name in ids:
            lvl = "P" if info["mentions"] >= 2 else "I"
            out[ids[name]] = (lvl, "syllabus signal", f"{info['mentions']} mention(s) in {label}; not yet reviewed", True)
    for rv in db.scalars(select(GapReview).where(GapReview.analysis_id == ga.id)):
        lvl = {"practiced": "P", "mentioned_only": "I"}.get(rv.faculty_status, "-")
        who = rv.reviewer.full_name if rv.reviewer else "faculty"
        out[rv.skill_id] = (lvl, "faculty review", f"{rv.faculty_status.replace('_', ' ')} — reviewed by {who} on {label}"
                            + (f": {rv.rationale}" if rv.rationale else ""), False)
    return out


def build(db: Session, program: Program, target: str = gapsvc.ALL, top_n: int = 20) -> dict:
    org = program.org_id
    courses = program_courses(program)
    demand, n_jobs = gapsvc.market_demand(db, target, org)
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
    for c, is_core in courses:
        syl_ev = latest_syllabus_evidence(db, org, c)
        cat = {cs.skill_id for cs in db.scalars(select(CourseSkill).where(CourseSkill.course_id == c.id, CourseSkill.weight >= 1.0))}
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
