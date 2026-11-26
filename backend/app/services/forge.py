"""CometForge — turn a gap analysis into an updated, future-ready syllabus.

Both engines (built-in and Claude) produce the same `ForgeSyllabus` schema, so the
editor, exports and knowledge-graph feedback work identically.
"""
import math
import re

from pydantic import BaseModel, Field

from ..data.forge_library import (
    ACCREDITATION, BLOOM_BY_CATEGORY, CATEGORY_TEMPLATE, DEFAULT_PROGRAM_GOALS, SKILL_CONTENT,
)
from ..data.taxonomy import SKILLS
from . import ai
from .skills import extract_builtin
from .gap import STATUS_W

CATEGORY_OF = {s[0]: s[1] for s in SKILLS}


class Outcome(BaseModel):
    id: str
    text: str
    bloom: str = "Apply"
    skills: list[str] = Field(default_factory=list)
    is_new: bool = False


class Module(BaseModel):
    week: int
    title: str
    topics: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    is_new: bool = False


class Assessment(BaseModel):
    name: str
    type: str
    weight: int
    description: str
    outcomes: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class Project(BaseModel):
    title: str
    description: str
    deliverables: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class AccreditationLink(BaseModel):
    standard: str
    outcomes: list[str] = Field(default_factory=list)
    evidence: str = ""


class GoalLink(BaseModel):
    goal: str
    outcomes: list[str] = Field(default_factory=list)


class ForgeSyllabus(BaseModel):
    course_code: str = ""
    course_title: str
    description: str
    framework: str = "AACSB"
    learning_outcomes: list[Outcome]
    modules: list[Module]
    assessments: list[Assessment]
    project: Project
    accreditation: list[AccreditationLink]
    program_goals: list[GoalLink]
    tools: list[str] = Field(default_factory=list)
    gaps_addressed: list[str] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list)


# ── helpers ────────────────────────────────────────────────────────────────────
_SKIP = re.compile(r"\b(exam|midterm|final|presentation|work session|review|holiday|break)\b", re.I)
_OBJ_HEAD = re.compile(r"(learning objectives|learning outcomes|course objectives|student learning outcomes)", re.I)
_NUM = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s+(.{12,})$")


def existing_objectives(raw: str, limit: int = 8) -> list[str]:
    lines, out, on = raw.splitlines(), [], False
    for ln in lines:
        if _OBJ_HEAD.search(ln):
            on = True
            continue
        if on:
            m = _NUM.match(ln)
            if m:
                out.append(m.group(1).strip().rstrip("."))
            elif ln.strip() and ln.strip().isupper():
                break
            if len(out) >= limit:
                break
    return out


def _skills_in(text: str, allowed: list[str], limit: int = 4) -> list[str]:
    found = extract_builtin(text)
    return [s for s in allowed if s in found][:limit]


def _tag_values(o: "Outcome") -> "Outcome":
    t = o.text.lower()
    if ("responsib" in t or "ethic" in t) and not ({"Responsible AI & AI Ethics", "Business Ethics"} & set(o.skills)):
        ai_cat = any(CATEGORY_OF.get(x) == "AI & Machine Learning" for x in o.skills)
        o.skills.append("Responsible AI & AI Ethics" if ai_cat else "Business Ethics")
    return o


def _content(skill: str) -> dict:
    if skill in SKILL_CONTENT:
        return SKILL_CONTENT[skill]
    cat = CATEGORY_OF.get(skill, "Professional Skills")
    t = CATEGORY_TEMPLATE.get(cat, CATEGORY_TEMPLATE["Professional Skills"])
    return {"title": skill, "topics": [f"{skill}: {t[0].lower()}", f"{skill}: {t[1].lower()}", f"{skill}: {t[2].lower()}"],
            "activity": f"{t[1]} focused on {skill}", "outcome": f"Apply {skill} to realistic business problems"}


def _bloom_sentence(skill: str, outcome: str) -> tuple[str, str]:
    verb = BLOOM_BY_CATEGORY.get(CATEGORY_OF.get(skill, ""), "Apply")
    return verb, outcome


def _map_standards(framework: str, outcomes: list[Outcome]) -> list[AccreditationLink]:
    fw = ACCREDITATION.get(framework)
    if not fw:
        return []
    links = []
    for std, keys in fw.items():
        hits = [o.id for o in outcomes if any(k in o.skills or any(CATEGORY_OF.get(s) == k for s in o.skills) for k in keys)]
        if hits:
            links.append(AccreditationLink(standard=std, outcomes=hits,
                                           evidence="Assessed through " + ("the team project and skill labs" if len(hits) > 1 else "a skill lab")))
    return links


def _map_goals(goals: list[str], outcomes: list[Outcome]) -> list[GoalLink]:
    kw = {
        "data": ["Analytics & Data", "AI & Machine Learning", "Finance", "Accounting", "Operations & Supply Chain", "Marketing"],
        "technolog": ["AI & Machine Learning", "Software & Cloud", "Information Systems", "Cybersecurity", "Analytics & Data"],
        "communicat": ["Professional Skills"], "collaborat": ["Professional Skills"], "team": ["Professional Skills"],
        "ethic": ["Responsible AI & AI Ethics", "Business Ethics", "Privacy & Data Protection"],
        "responsib": ["Responsible AI & AI Ethics", "Business Ethics"],
    }
    out = []
    for g in goals:
        keys = {c for k, cats in kw.items() if k in g.lower() for c in cats}
        hits = [o.id for o in outcomes if any(s in keys or CATEGORY_OF.get(s) in keys for s in o.skills)] if keys else []
        out.append(GoalLink(goal=g, outcomes=hits))
    return out


# ── built-in engine ────────────────────────────────────────────────────────────
def build_builtin(syl, analysis: dict | None, focus: list[str], weeks: int, framework: str, goals: list[str]) -> ForgeSyllabus:
    covered = [ss.skill.name for ss in sorted(syl.skills, key=lambda s: -s.mentions)]
    change_log: list[str] = []
    gap_info = {g["name"]: g for g in (analysis or {}).get("gaps", [])}

    # 1. existing schedule (minus exams/presentations which we re-add)
    existing = [t for t in (syl.topics or []) if not _SKIP.search(t)]
    if not existing:
        existing = [f"{s}" for s in covered[:max(weeks - 6, 4)]]
    # 2. new modules: one per focus skill, paired when two skills share a category
    new_mods: list[Module] = []
    # Professional skills are woven into the project and assessments, not taught as a standalone week
    woven = [f for f in focus if CATEGORY_OF.get(f) == "Professional Skills"]
    pending = [f for f in focus if f not in woven]
    while pending:
        s = pending.pop(0)
        partner = next((p for p in pending if CATEGORY_OF.get(p) == CATEGORY_OF.get(s) and p not in SKILL_CONTENT and s not in SKILL_CONTENT), None)
        c = _content(s)
        skills = [s]
        topics, acts = list(c["topics"]), [c["activity"]]
        if partner:
            pending.remove(partner)
            pc = _content(partner)
            skills.append(partner)
            topics = topics[:2] + pc["topics"][:2]
            acts.append(pc["activity"])
        new_mods.append(Module(week=0, title=c["title"] if not partner else f"{c['title']} & {pc['title']}",
                               topics=topics, skills=skills, activities=acts, is_new=True))
    # 3. fit into the term: reserve 2 weeks (midterm + project presentations)
    capacity = weeks - 2 - len(new_mods)
    if capacity < 3:  # too many new modules: keep the most important ones
        keep = max(weeks - 2 - 3, 1)
        dropped = new_mods[keep:]
        new_mods = new_mods[:keep]
        capacity = weeks - 2 - len(new_mods)
        if dropped:
            change_log.append(f"Not enough weeks for: {', '.join(s for m in dropped for s in m.skills)} — consider a follow-on course.")
    merged = list(existing)
    while len(merged) > capacity:  # merge the two shortest adjacent topics
        i = min(range(len(merged) - 1), key=lambda k: len(merged[k]) + len(merged[k + 1]))
        merged[i: i + 2] = [f"{merged[i]}; {merged[i + 1]}"]
    if len(merged) < len(existing):
        change_log.append(f"Condensed {len(existing)} existing topic weeks into {len(merged)} to make room for new content.")

    existing_mods = [Module(week=0, title=t.split(";")[0][:90], topics=[p.strip() for p in t.split(";")],
                            skills=_skills_in(t, covered)) for t in merged]
    # place half the new modules after the first ~40% of existing material (foundations first), the rest near the end
    cut = max(1, math.ceil(len(existing_mods) * 0.4))
    first = math.ceil(len(new_mods) / 2)
    schedule = existing_mods[:cut] + new_mods[:first] + existing_mods[cut:] + new_mods[first:]
    schedule.insert(len(schedule) // 2, Module(week=0, title="Midterm exam", topics=["Review and midterm exam"]))
    schedule.append(Module(week=0, title="Team project presentations", topics=["Industry-aligned project presentations and peer review"],
                           skills=["Communication", "Teamwork & Collaboration"]))
    for i, m in enumerate(schedule, 1):
        m.week = i
        if m.is_new:
            g = gap_info.get(m.skills[0])
            why = f" — {g['priority']} gap, in {round(g['demand'] * 100)}% of postings" if g else ""
            change_log.append(f"Added Week {i}: {m.title}{why}.")

    for w in woven:
        change_log.append(f"Integrated {w} into the team project (structured roles, checkpoints and peer evaluation) rather than a standalone week.")

    # 4. learning outcomes: keep originals, add one per new skill
    outcomes: list[Outcome] = []
    for i, text in enumerate(existing_objectives(syl.raw_text) or [f"Apply {s} in business contexts" for s in covered[:4]], 1):
        outcomes.append(_tag_values(Outcome(id=f"LO{i}", text=text, bloom="Apply", skills=_skills_in(text, covered, 3))))
    for m in new_mods:
        for s in m.skills:
            verb, text = _bloom_sentence(s, _content(s)["outcome"])
            lo = _tag_values(Outcome(id=f"LO{len(outcomes) + 1}", text=text, bloom=verb, skills=[s], is_new=True))
            outcomes.append(lo)
            m.outcomes.append(lo.id)
            change_log.append(f"New learning outcome {lo.id}: {text}.")
    if not any(CATEGORY_OF.get(x) == "Professional Skills" for o in outcomes for x in o.skills):
        lo = Outcome(id=f"LO{len(outcomes) + 1}", text="Communicate data-driven recommendations to stakeholders and collaborate effectively in a team",
                     bloom="Apply", skills=["Communication", "Teamwork & Collaboration"], is_new=True)
        outcomes.append(lo)
        change_log.append(f"New learning outcome {lo.id}: {lo.text} (assessed by the team project).")
    for m in schedule:
        if not m.outcomes:
            m.outcomes = [o.id for o in outcomes if set(o.skills) & set(m.skills)][:2]

    # 5. assessments & project
    new_skills = [s for m in new_mods for s in m.skills]
    addressed = new_skills + woven
    lab_lo = [o.id for o in outcomes if o.is_new]
    project_skills = (new_skills[:3] + covered[:3])[:6]
    target = (analysis or {}).get("target", "industry")
    if target.startswith("Sample: "):  # a documented job sample: describe the market by its main role family instead
        roles = ((analysis or {}).get("provenance") or {}).get("role_families") or {}
        target = next(iter(roles), "All roles")
    project = Project(
        title=f"Industry Challenge: {syl.title} in Practice",
        description=(f"Teams act as analysts for a {target if target != 'All roles' else 'partner'} employer. Using a real dataset, they "
                     f"apply {', '.join(project_skills[:-1])} and {project_skills[-1] if project_skills else 'course methods'} to a business question "
                     "and recommend actions to an industry panel."),
        deliverables=["Project charter and data plan (Week 4)", "Interim checkpoint with working analysis", "Final report and reproducible files",
                      "15-minute presentation to an industry panel", "Peer evaluation"],
        skills=list(dict.fromkeys(project_skills + ["Communication", "Teamwork & Collaboration"] + woven)))
    assessments = [
        Assessment(name="Skill labs", type="lab", weight=25, description="Hands-on labs: " + "; ".join(a for m in new_mods for a in m.activities[:1]) if new_mods else "Weekly hands-on labs",
                   outcomes=lab_lo, skills=new_skills),
        Assessment(name="Homework assignments", type="assignment", weight=15, description="Problem sets applying weekly material",
                   outcomes=[o.id for o in outcomes if not o.is_new][:4], skills=covered[:4]),
        Assessment(name="Midterm exam", type="exam", weight=20, description="Concepts and applied problems from weeks 1–midterm",
                   outcomes=[o.id for o in outcomes][:5]),
        Assessment(name="Industry team project", type="project", weight=30, description=project.description,
                   outcomes=[o.id for o in outcomes], skills=project.skills),
        Assessment(name="Participation & AI-use reflections", type="participation", weight=10,
                   description="In-class activities and short reflections on responsible tool use"),
    ]
    change_log.append("Rebalanced assessment: 25% hands-on skill labs and a 30% industry-aligned team project.")

    tools = sorted({s for s in new_skills + covered if s in ("Python", "R", "SQL", "Excel", "Tableau", "Power BI", "AWS", "Microsoft Azure",
                                                             "Google Cloud", "Git & Version Control", "ERP Systems (SAP/Oracle)")})
    desc = (f"{syl.title} develops {', '.join(covered[:3]) or 'core analytical skills'} and now adds "
            f"{', '.join(new_skills[:4]) or 'current industry practice'}"
            f" — skills employers request in current {target} postings. Students practice through hands-on labs and an industry-aligned team project.")
    return ForgeSyllabus(course_code=syl.code or "", course_title=syl.title, description=desc, framework=framework,
                         learning_outcomes=outcomes, modules=schedule, assessments=assessments, project=project,
                         accreditation=_map_standards(framework, outcomes), program_goals=_map_goals(goals, outcomes),
                         tools=tools, gaps_addressed=addressed, change_log=change_log)


# ── Claude engine ──────────────────────────────────────────────────────────────
def build_ai(syl, analysis: dict | None, focus: list[str], weeks: int, framework: str, goals: list[str]) -> ForgeSyllabus | None:
    if not ai.enabled():
        return None
    gaps = "\n".join(f"- {g['name']}: {g['status']}, {round(g['demand']*100)}% of postings, {g['priority']}"
                     for g in (analysis or {}).get("gaps", []) if g["name"] in focus)
    standards = ", ".join(ACCREDITATION.get(framework, {})) or "none"
    res = ai.structured(
        system=("You are an expert instructional designer for a business school. You revise syllabi so they stay rigorous while "
                "closing documented industry skill gaps. Keep the course's identity and strongest existing content; add new material "
                "only where it serves the gaps. Use measurable, Bloom-aligned learning outcomes (ids LO1, LO2, …). Assessment weights must "
                "sum to 100. Mark new modules/outcomes with is_new=true. Skill names must come from the gap list or the course's existing "
                "skills. Write change_log entries as short sentences explaining each change and why."),
        prompt=(f"Existing syllabus:\n<syllabus>\n{syl.raw_text[:40000]}\n</syllabus>\n\n"
                f"Gaps to close (target market: {(analysis or {}).get('target', 'industry')}):\n{gaps or '- none listed'}\n\n"
                f"Existing course skills: {', '.join(ss.skill.name for ss in syl.skills)}\n"
                f"Term length: {weeks} weeks (include a midterm and final project presentations).\n"
                f"Accreditation framework: {framework} — map outcomes to these standards: {standards}.\n"
                f"Program goals: {'; '.join(goals)}\n"
                f"course_code: {syl.code or ''}; course_title: {syl.title}; framework: {framework}; "
                f"gaps_addressed: the focus skills you actually added."),
        schema=ForgeSyllabus, effort="medium", max_tokens=32000)
    if res:
        total = sum(a.weight for a in res.assessments)
        if total != 100 and total > 0:  # normalize weights defensively
            for a in res.assessments:
                a.weight = round(a.weight * 100 / total)
    return res


def generate(syl, analysis: dict | None, focus: list[str], weeks: int = 15, framework: str = "AACSB",
             goals: list[str] | None = None) -> tuple[ForgeSyllabus, str]:
    goals = goals or DEFAULT_PROGRAM_GOALS
    weeks = max(8, min(weeks, 18))
    res = build_ai(syl, analysis, focus, weeks, framework, goals)
    if res:
        return res, "claude"
    return build_builtin(syl, analysis, focus, weeks, framework, goals), "builtin"


def projected_score(analysis: dict, added: set[str]) -> float:
    """Coverage score if the draft's newly added skills were taught (status → covered)."""
    rows = analysis.get("skills", [])
    total = sum(r["demand"] for r in rows) or 1
    return round(100 * sum(r["demand"] * (1.0 if r["name"] in added else STATUS_W[r["status"]]) for r in rows) / total, 1)


def to_text(c: ForgeSyllabus) -> str:
    """Plain-text rendering (used for exports and re-analysis)."""
    lines = [f"{c.course_code} {c.course_title}".strip(), "", "COURSE DESCRIPTION", c.description, "", "LEARNING OUTCOMES"]
    lines += [f"{o.id}. {o.text}" for o in c.learning_outcomes]
    lines += ["", "COURSE SCHEDULE"]
    for m in c.modules:
        lines.append(f"Week {m.week}: {m.title}" + (f" — {'; '.join(m.topics)}" if m.topics else ""))
    lines += ["", "ASSESSMENT"] + [f"{a.name} ({a.type}) {a.weight}% — {a.description}" for a in c.assessments]
    lines += ["", "TEAM PROJECT", c.project.title, c.project.description] + [f"- {d}" for d in c.project.deliverables]
    return "\n".join(lines)
