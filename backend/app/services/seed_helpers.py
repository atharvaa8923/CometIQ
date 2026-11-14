"""Helpers shared by the seeder and catalog imports."""
from sqlalchemy.orm import Session

from ..models import Course, CourseSkill
from . import skills as sk


def map_course_skills(db: Session, course: Course, ids: dict[str, int]) -> None:
    text = f"{course.title}. {course.title}. {course.description or ''}"  # title weighted x2
    found = sk.extract_builtin(text)
    course.skills.clear()
    db.flush()
    for name, info in found.items():
        if name in ids:
            in_title = name in sk.extract_builtin(course.title)
            course.skills.append(CourseSkill(skill_id=ids[name], weight=1.0 if in_title or info["mentions"] > 1 else 0.6))
