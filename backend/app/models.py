"""CometIQ data model — one shared knowledge graph for all four modules.

Jobs ─ Skills ─ Courses ─ Programs ─ Students ─ Projects ─ Employers ─ Outcomes
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLES = ("admin", "faculty", "student", "employer", "advisor")


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Tenancy & users ────────────────────────────────────────────────────────────
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    join_code: Mapped[str] = mapped_column(String(40), unique=True)
    plan: Mapped[str] = mapped_column(String(30), default="pro")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    company: Mapped[str | None] = mapped_column(String(200))  # employers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # tokens issued earlier are revoked
    consent_version: Mapped[str | None] = mapped_column(String(20))  # privacy notice / terms version accepted
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    org: Mapped[Organization] = relationship()


# ── Skills (global taxonomy) ───────────────────────────────────────────────────
class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    is_emerging: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Catalog ────────────────────────────────────────────────────────────────────
class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("org_id", "code"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20), index=True)
    subject: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str] = mapped_column(String(300))
    credits: Mapped[int] = mapped_column(Integer, default=3)
    description: Mapped[str | None] = mapped_column(Text)

    skills: Mapped[list["CourseSkill"]] = relationship(cascade="all, delete-orphan")


class CoursePrereq(Base):
    """Prereq edge. Edges of one course with the same `group` are OR'd; groups are AND'd."""
    __tablename__ = "course_prereqs"
    __table_args__ = (UniqueConstraint("course_id", "requires_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    requires_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    group: Mapped[int] = mapped_column(Integer, default=0)


class CourseSkill(Base):
    __tablename__ = "course_skills"
    __table_args__ = (UniqueConstraint("course_id", "skill_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="catalog")  # catalog|syllabus|forge

    skill: Mapped[Skill] = relationship()


class Program(Base):
    __tablename__ = "programs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(40))
    department: Mapped[str | None] = mapped_column(String(200))
    total_sch: Mapped[int] = mapped_column(Integer, default=36)
    core_sch: Mapped[int] = mapped_column(Integer, default=0)
    elective_sch: Mapped[int] = mapped_column(Integer, default=0)
    is_stem: Mapped[bool] = mapped_column(Boolean, default=False)
    catalog_url: Mapped[str | None] = mapped_column(String(500))
    prereq_notes: Mapped[str | None] = mapped_column(Text)
    catalog_year: Mapped[str | None] = mapped_column(String(20))           # e.g. "2025-26"
    catalog_confirmed_by: Mapped[str | None] = mapped_column(String(200))  # program owner who confirmed it
    catalog_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    catalog_note: Mapped[str | None] = mapped_column(Text)

    core: Mapped[list["ProgramCore"]] = relationship(cascade="all, delete-orphan", order_by="ProgramCore.sort")
    concentrations: Mapped[list["Concentration"]] = relationship(cascade="all, delete-orphan")


class ProgramCore(Base):
    """Core requirement. or_group > 0: any one course of the group satisfies the slot."""
    __tablename__ = "program_core"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    or_group: Mapped[int] = mapped_column(Integer, default=0)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped[Course] = relationship()


class Concentration(Base):
    __tablename__ = "concentrations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    required_sch: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    courses: Mapped[list["ConcentrationCourse"]] = relationship(cascade="all, delete-orphan")


class ConcentrationCourse(Base):
    __tablename__ = "concentration_courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concentration_id: Mapped[str] = mapped_column(ForeignKey("concentrations.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))

    course: Mapped[Course] = relationship()


# ── Industry demand ────────────────────────────────────────────────────────────
class Job(Base):
    """A job posting. org_id NULL = shared market data; employer_id set = posted in CometMatch."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    employer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    role_family: Mapped[str | None] = mapped_column(String(80), index=True)
    employment_type: Mapped[str] = mapped_column(String(40), default="Full-time")
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    skills: Mapped[list["JobSkill"]] = relationship(cascade="all, delete-orphan")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    importance: Mapped[str] = mapped_column(String(20), default="required")  # required|preferred

    skill: Mapped[Skill] = relationship()


# ── CometGap ───────────────────────────────────────────────────────────────────
class Syllabus(Base):
    __tablename__ = "syllabi"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    code: Mapped[str | None] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(300))
    semester: Mapped[str | None] = mapped_column(String(40))
    filename: Mapped[str | None] = mapped_column(String(300))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    topics: Mapped[list] = mapped_column(JSON, default=list)
    pilot_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    approved_by: Mapped[str | None] = mapped_column(String(200))   # who approved its use (e.g. instructor / chair)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    skills: Mapped[list["SyllabusSkill"]] = relationship(cascade="all, delete-orphan")
    analyses: Mapped[list["GapAnalysis"]] = relationship(cascade="all, delete-orphan", order_by="GapAnalysis.created_at.desc()")


class SyllabusSkill(Base):
    __tablename__ = "syllabus_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    mentions: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[str | None] = mapped_column(Text)
    excerpts: Mapped[list | None] = mapped_column(JSON)  # up to 3 syllabus lines where the skill appears

    skill: Mapped[Skill] = relationship()


class JobSample(Base):
    """A documented, frozen set of job postings used as the market evidence for gap analyses."""
    __tablename__ = "job_samples"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(Text, default="")        # how/why these postings were selected
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)    # role family, sources, date range, location, query
    job_ids: Mapped[list] = mapped_column(JSON, default=list)     # frozen at creation
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GapReview(Base):
    """Faculty judgment on one skill of one analysis. The system only sees mentions; faculty decide
    whether students actually practice or demonstrate the skill."""
    __tablename__ = "gap_reviews"
    __table_args__ = (UniqueConstraint("analysis_id", "skill_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("gap_analyses.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    system_status: Mapped[str] = mapped_column(String(20))   # covered | partial | missing (mention-based)
    faculty_status: Mapped[str] = mapped_column(String(20))  # practiced | mentioned_only | not_covered | not_relevant
    decision: Mapped[str] = mapped_column(String(20))        # confirmed | corrected
    rationale: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(20), default="none")  # none | planned | done
    action_note: Mapped[str | None] = mapped_column(Text)
    carried_from: Mapped[str | None] = mapped_column(String(32))     # analysis id the review was copied from
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    skill: Mapped[Skill] = relationship()
    reviewer: Mapped[User | None] = relationship()


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(String(120))  # role family or "All roles"
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("job_samples.id", ondelete="SET NULL", name="fk_gap_analyses_sample_id"))
    score: Mapped[float] = mapped_column(Float)
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(20), default="builtin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── CometForge ─────────────────────────────────────────────────────────────────
class ForgeDraft(Base):
    __tablename__ = "forge_drafts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    syllabus_id: Mapped[str | None] = mapped_column(ForeignKey("syllabi.id", ondelete="SET NULL"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("gap_analyses.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved
    content: Mapped[dict] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(20), default="builtin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── CometPath ──────────────────────────────────────────────────────────────────
class StudentProfile(Base):
    __tablename__ = "student_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"))
    concentration_id: Mapped[str | None] = mapped_column(ForeignKey("concentrations.id", ondelete="SET NULL"))
    career_goal: Mapped[str | None] = mapped_column(String(80))
    start_term: Mapped[str] = mapped_column(String(20), default="Fall 2026")
    credits_per_term: Mapped[int] = mapped_column(Integer, default=9)
    include_summer: Mapped[bool] = mapped_column(Boolean, default=False)
    headline: Mapped[str | None] = mapped_column(String(300))
    resume_filename: Mapped[str | None] = mapped_column(String(300))
    resume_text: Mapped[str | None] = mapped_column(Text)
    resume_skills: Mapped[list] = mapped_column(JSON, default=list)  # skill ids
    open_to_match: Mapped[bool] = mapped_column(Boolean, default=True)


class StudentCourse(Base):
    __tablename__ = "student_courses"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))  # completed|enrolled|planned
    term: Mapped[str | None] = mapped_column(String(20))
    grade: Mapped[str | None] = mapped_column(String(4))

    course: Mapped[Course] = relationship()


# ── CometMatch ─────────────────────────────────────────────────────────────────
class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "student_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="applied")  # applied|shortlisted|interview|offer|rejected
    initiated_by: Mapped[str] = mapped_column(String(20), default="student")  # student|employer
    score: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    job: Mapped[Job] = relationship()
    student: Mapped[User] = relationship()


class Evidence(Base):
    """Student-submitted proof of a skill: a course, certification, project or experience.
    Verified evidence counts as full skill evidence in CometMatch; verified certifications add bonus points."""
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # course | certification | project | experience
    title: Mapped[str] = mapped_column(String(300))
    issuer: Mapped[str | None] = mapped_column(String(200))
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)  # skill ids
    credential_id: Mapped[str | None] = mapped_column(String(200))
    credential_url: Mapped[str | None] = mapped_column(String(1000))
    issued_on: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | verified | rejected
    bonus_points: Mapped[int] = mapped_column(Integer, default=0)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    student: Mapped[User] = relationship(foreign_keys=[student_id])
    course: Mapped[Course | None] = relationship()
    file: Mapped["EvidenceFile | None"] = relationship(cascade="all, delete-orphan", uselist=False)


class EvidenceFile(Base):
    """Uploaded certificate/transcript. Stored in the database so deployments need no persistent disk."""
    __tablename__ = "evidence_files"
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class PlanReview(Base):
    """A degree plan submitted by a student for advisor review."""
    __tablename__ = "plan_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    advisor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)  # submitted | approved | changes_requested
    snapshot: Mapped[dict] = mapped_column(JSON)  # program, concentration, goal, terms, readiness at submission
    student_note: Mapped[str | None] = mapped_column(Text)
    advisor_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[User] = relationship(foreign_keys=[student_id])
    advisor: Mapped[User | None] = relationship(foreign_keys=[advisor_id])


class SyncRun(Base):
    """One job-market sync. run_key is unique for nightly runs so only one server instance runs it."""
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_key: Mapped[str | None] = mapped_column(String(60), unique=True)
    trigger: Mapped[str] = mapped_column(String(20))  # nightly | manual
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | partial | failed
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    """Single-use password reset token (only its SHA-256 hash is stored)."""
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(Base):
    """In-app notification (also emailed when the user has email notifications on)."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Task(Base):
    """Background job (AI analysis, syllabus generation, email). Claimed atomically so several workers can run."""
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str | None] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued | running | done | failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiUsage(Base):
    """Claude calls per organization per day (enforces AI_DAILY_LIMIT_PER_ORG)."""
    __tablename__ = "ai_usage"
    __table_args__ = (UniqueConstraint("org_id", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    day: Mapped[str] = mapped_column(String(10))
    calls: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str | None] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
