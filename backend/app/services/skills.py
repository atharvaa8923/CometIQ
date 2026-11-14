"""Skill extraction: taxonomy matching (built-in) + optional Claude enrichment."""
import re
from collections import defaultdict
from functools import lru_cache

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import SKILLS
from ..models import Skill
from . import ai


@lru_cache
def _matchers() -> list[tuple[str, list[re.Pattern]]]:
    out = []
    for name, _cat, aliases, _em in SKILLS:
        pats = []
        # The skill name is itself an alias unless it is a 1–2 letter token (e.g. "R").
        all_aliases = set(aliases) | ({name.lower()} if len(name) > 2 else set())
        for a in all_aliases:
            if a.startswith("="):
                pats.append(re.compile(rf"(?<![\w/+#-]){re.escape(a[1:])}(?![\w+#-])"))
            else:
                pats.append(re.compile(rf"(?<![\w]){re.escape(a.lower())}(?![\w])", re.I))
        out.append((name, pats))
    return out


def _snippet(text: str, start: int, end: int, pad: int = 70) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s else "") + " ".join(text[s:e].split()) + ("…" if e < len(text) else "")


def extract_builtin(text: str) -> dict[str, dict]:
    """Return {skill_name: {"mentions": int, "evidence": str}} for skills found in text."""
    found: dict[str, dict] = {}
    if not text:
        return found
    for name, pats in _matchers():
        count, first = 0, None
        for p in pats:
            for m in p.finditer(text):
                count += 1
                if first is None or m.start() < first[0]:
                    first = (m.start(), m.end())
        if count:
            found[name] = {"mentions": count, "evidence": _snippet(text, *first)}
    return found


class _AISkill(BaseModel):
    skill: str
    evidence: str
    importance: str  # required | preferred


class _AISkills(BaseModel):
    skills: list[_AISkill]


def extract(text: str, kind: str = "document") -> tuple[dict[str, dict], str]:
    """Hybrid extraction. Returns (skills, engine). Claude can only choose skills from the
    taxonomy, so results stay comparable across syllabi, jobs and resumes."""
    found = extract_builtin(text)
    if not ai.enabled() or len(text.strip()) < 40:
        return found, "builtin"
    names = [s[0] for s in SKILLS]
    res = ai.structured(
        system=(
            "You map documents onto a fixed skill taxonomy for a university/workforce analytics platform. "
            "Only return skills from the provided list, spelled exactly as listed. Include a skill only when the "
            "document clearly teaches, requires or demonstrates it, including when it is described without the exact keyword. "
            "evidence: a short quote or paraphrase from the document. importance: 'required' or 'preferred' "
            "(for syllabi and resumes always 'required')."
        ),
        prompt=f"Skill taxonomy:\n{', '.join(names)}\n\nDocument type: {kind}\n\n<document>\n{text[:60000]}\n</document>",
        schema=_AISkills,
        effort="low",
        max_tokens=8000,
    )
    if res is None:
        return found, "builtin"
    lookup = {n.lower(): n for n in names}
    for s in res.skills:
        n = lookup.get(s.skill.strip().lower())
        if not n:
            continue
        if n in found:
            found[n]["mentions"] += 1
        else:
            found[n] = {"mentions": 1, "evidence": s.evidence[:300], "importance": s.importance}
    return found, "claude"


def skill_ids(db: Session, names) -> dict[str, int]:
    names = list(names)
    if not names:
        return {}
    rows = db.execute(select(Skill.name, Skill.id).where(Skill.name.in_(names))).all()
    return {n: i for n, i in rows}


def importance_from_context(text: str, evidence: str) -> str:
    """Heuristic for job postings: mentions in a 'preferred / nice to have' context are preferred."""
    e = (evidence or "").lower()
    return "preferred" if any(k in e for k in ("preferred", "nice to have", "a plus", "bonus", "desired")) else "required"


def category_counts(skill_names) -> dict[str, int]:
    cat = {s[0]: s[1] for s in SKILLS}
    out: dict[str, int] = defaultdict(int)
    for n in skill_names:
        out[cat.get(n, "Other")] += 1
    return dict(out)
