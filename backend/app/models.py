"""CometIQ data model — one shared knowledge graph for all four modules.

Jobs ─ Skills ─ Courses ─ Programs ─ Students ─ Projects ─ Employers ─ Outcomes
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, false, true,
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

    skill: Mapped[Skill] = relationship(lazy="joined")


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

    course: Mapped[Course] = relationship(lazy="joined")


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

    course: Mapped[Course] = relationship(lazy="joined")


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

    skills: Mapped[list["JobSkill"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    importance: Mapped[str] = mapped_column(String(20), default="required")  # required|preferred

    skill: Mapped[Skill] = relationship(lazy="joined")


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
    canvas_course_id: Mapped[str | None] = mapped_column(String(40), index=True)   # imported from this Canvas course
    pilot_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    approved_by: Mapped[str | None] = mapped_column(String(200))   # who approved its use (e.g. instructor / chair)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    skills: Mapped[list["SyllabusSkill"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    analyses: Mapped[list["GapAnalysis"]] = relationship(cascade="all, delete-orphan", order_by="GapAnalysis.created_at.desc()")


class SyllabusSkill(Base):
    __tablename__ = "syllabus_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    mentions: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[str | None] = mapped_column(Text)
    excerpts: Mapped[list | None] = mapped_column(JSON)  # up to 3 syllabus lines where the skill appears

    skill: Mapped[Skill] = relationship(lazy="joined")


class JobSample(Base):
    """A documented, frozen set of job postings used as the market evidence for gap analyses."""
    __tablename__ = "job_samples"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(Text, default="")        # how/why these postings were selected
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)    # role family, sources, date range, location, query
    job_ids: Mapped[list] = mapped_column(JSON, default=list)     # frozen at creation
    # documented = created by faculty with a method; auto = snapshot of the live postings taken by an analysis
    kind: Mapped[str] = mapped_column(String(20), default="documented", server_default="documented")
    # {job_id: {"source", "posted", "role", "skills": [[skill name, importance], ...]}} — the demand inputs, frozen,
    # so a report can be recomputed even after postings are re-extracted, closed or deleted
    snapshot: Mapped[dict | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SyllabusVersion(Base):
    """One saved version of a course syllabus (usually one per semester), with the skills extracted from it."""
    __tablename__ = "syllabus_versions"
    __table_args__ = (UniqueConstraint("syllabus_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    semester: Mapped[str | None] = mapped_column(String(40))
    filename: Mapped[str | None] = mapped_column(String(300))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64))
    topics: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[dict] = mapped_column(JSON, default=dict)     # {skill name: {"mentions", "excerpts"}}
    extraction_engine: Mapped[str] = mapped_column(String(20), default="builtin")
    taxonomy_version: Mapped[str | None] = mapped_column(String(20))
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CatalogVersion(Base):
    """Catalog entry for a course (title, description, prerequisites, programs and catalog year) as used by an analysis."""
    __tablename__ = "catalog_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    course_code: Mapped[str] = mapped_column(String(30), index=True)
    catalog_year: Mapped[str | None] = mapped_column(String(20))
    content_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
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

    skill: Mapped[Skill] = relationship(lazy="joined")
    reviewer: Mapped[User | None] = relationship()


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(String(120))  # role family or "All roles"
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("job_samples.id", ondelete="SET NULL", name="fk_gap_analyses_sample_id"))
    # recorded inputs: with these an analysis can be recomputed exactly (null on analyses made before versioning)
    syllabus_version_id: Mapped[str | None] = mapped_column(ForeignKey("syllabus_versions.id", ondelete="SET NULL", name="fk_gap_analyses_syllabus_version_id"))
    catalog_version_id: Mapped[str | None] = mapped_column(ForeignKey("catalog_versions.id", ondelete="SET NULL", name="fk_gap_analyses_catalog_version_id"))
    scoring_version: Mapped[str | None] = mapped_column(String(20))
    taxonomy_version: Mapped[str | None] = mapped_column(String(20))
    top_n: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(20), default="builtin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GapDecision(Base):
    """What faculty decided to do about a reviewed gap. A new decision for the same course and skill supersedes the
    previous one, which is kept as history. Evidence records exactly which inputs the decision was based on."""
    __tablename__ = "gap_decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("gap_analyses.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(30))   # add_here | covered_elsewhere | defer | out_of_scope
    rationale: Mapped[str] = mapped_column(Text)
    covered_in: Mapped[list | None] = mapped_column(JSON)          # course codes, for covered_elsewhere
    revisit_term: Mapped[str | None] = mapped_column(String(40))   # for defer
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_name: Mapped[str | None] = mapped_column(String(200))  # as it was when decided; cleared if the account is deleted
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)      # syllabus/sample/catalog/scoring versions + review
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | drafted | implemented | superseded
    forge_draft_id: Mapped[str | None] = mapped_column(ForeignKey("forge_drafts.id", ondelete="SET NULL", name="fk_gap_decisions_forge_draft_id"))
    detected_in_version: Mapped[int | None] = mapped_column(Integer)  # syllabus version whose mention signal suggests it was done
    implemented_note: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[str | None] = mapped_column(String(32))
    # faculty may share an accepted addition with employer partners, who can then offer a project or dataset
    share_with_partners: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    partner_note: Mapped[str | None] = mapped_column(Text)

    skill: Mapped[Skill] = relationship(lazy="joined")


class CurriculumProposal(Base):
    """A proposed syllabus change reviewed like a pull request: diff against the current version, evidence,
    line comments, approvals, then adoption as the next syllabus version. The proposed text is frozen per revision."""
    __tablename__ = "curriculum_proposals"
    __table_args__ = (UniqueConstraint("org_id", "number"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str | None] = mapped_column(String(200))
    # draft | in_review | changes_requested | approved | adopted | withdrawn
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    base_version_id: Mapped[str | None] = mapped_column(ForeignKey("syllabus_versions.id", ondelete="SET NULL", name="fk_proposals_base_version_id"))
    forge_draft_id: Mapped[str | None] = mapped_column(ForeignKey("forge_drafts.id", ondelete="SET NULL", name="fk_proposals_forge_draft_id"))
    proposed_text: Mapped[str] = mapped_column(Text, default="")
    proposed_content: Mapped[dict | None] = mapped_column(JSON)
    decision_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    effective_term: Mapped[str | None] = mapped_column(String(40))
    required_approvals: Mapped[int] = mapped_column(Integer, default=2)
    adopted_version_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comments: Mapped[list["ProposalComment"]] = relationship(cascade="all, delete-orphan", order_by="ProposalComment.created_at")
    reviews: Mapped[list["ProposalReview"]] = relationship(cascade="all, delete-orphan", order_by="ProposalReview.created_at")


class ProposalComment(Base):
    __tablename__ = "proposal_comments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("curriculum_proposals.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str | None] = mapped_column(String(200))
    anchor: Mapped[str | None] = mapped_column(String(40))       # e.g. "L12" (current line) or "R30" (proposed line)
    anchor_text: Mapped[str | None] = mapped_column(Text)        # the line as it was when commented
    revision: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProposalReview(Base):
    __tablename__ = "proposal_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("curriculum_proposals.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_name: Mapped[str | None] = mapped_column(String(200))
    vote: Mapped[str] = mapped_column(String(20))                # approve | request_changes
    body: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CurriculumMapEntry(Base):
    """Faculty-set level at which a course addresses a skill within a program (AACSB-style I/P/M curriculum map)."""
    __tablename__ = "curriculum_map_entries"
    __table_args__ = (UniqueConstraint("program_id", "course_id", "skill_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(2))                # I | P | M | "-" (not addressed)
    rationale: Mapped[str | None] = mapped_column(Text)
    set_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    set_by_name: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SkillBadge(Base):
    """A faculty-verified skill: the course is confirmed by faculty to have students practice (or master) the skill,
    and the student's completion of that course was verified by an advisor or administrator."""
    __tablename__ = "skill_badges"
    __table_args__ = (UniqueConstraint("student_id", "skill_id", "course_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    course_code: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(20), default="practiced")   # practiced | mastered
    term: Mapped[str | None] = mapped_column(String(40))
    basis: Mapped[dict] = mapped_column(JSON, default=dict)               # faculty basis + completion verification
    status: Mapped[str] = mapped_column(String(20), default="active")     # active | revoked
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    public_token: Mapped[str] = mapped_column(String(40), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    partner: Mapped[str | None] = mapped_column(String(200))      # employer whose sponsored project the student completed
    project_id: Mapped[str | None] = mapped_column(String(32))
    credentials_assertion_id: Mapped[str | None] = mapped_column(String(80))   # sent to Canvas Credentials (Badgr)
    credentials_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credentials_error: Mapped[str | None] = mapped_column(Text)

    skill: Mapped[Skill] = relationship(lazy="joined")
    course: Mapped[Course] = relationship(lazy="joined")


class SkillStack(Base):
    """A role-ready credential: a set of skills, each at a minimum level, earned through faculty-verified badges."""
    __tablename__ = "skill_stacks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role_family: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)   # [{"skill_id": int, "level": "practiced"|"mastered"}]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StackSubscription(Base):
    __tablename__ = "stack_subscriptions"
    __table_args__ = (UniqueConstraint("stack_id", "employer_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stack_id: Mapped[str] = mapped_column(ForeignKey("skill_stacks.id", ondelete="CASCADE"), index=True)
    employer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StackCompletion(Base):
    __tablename__ = "stack_completions"
    __table_args__ = (UniqueConstraint("stack_id", "student_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stack_id: Mapped[str] = mapped_column(ForeignKey("skill_stacks.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SponsoredProject(Base):
    """An employer's project, dataset or guest session offered for a gap faculty decided to add to a course."""
    __tablename__ = "sponsored_projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("gap_decisions.id", ondelete="SET NULL"))
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    employer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    company: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="project")   # project | dataset | guest_session
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    dataset_url: Mapped[str | None] = mapped_column(String(1000))
    deliverables: Mapped[list] = mapped_column(JSON, default=list)
    term: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="offered", index=True)  # offered|accepted|declined|completed|withdrawn
    faculty_note: Mapped[str | None] = mapped_column(Text)
    decided_by_name: Mapped[str | None] = mapped_column(String(200))
    forge_draft_id: Mapped[str | None] = mapped_column(ForeignKey("forge_drafts.id", ondelete="SET NULL", name="fk_sponsored_forge_draft_id"))
    participants: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    skill: Mapped[Skill] = relationship(lazy="joined")


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

    course: Mapped[Course] = relationship(lazy="joined")


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


# ── Integrations ───────────────────────────────────────────────────────────────
class UserIdentity(Base):
    """An external sign-in linked to a CometIQ account (single sign-on). The subject is the identity provider's stable id."""
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(300))     # the issuer URL
    subject: Mapped[str] = mapped_column(String(255))
    netid: Mapped[str | None] = mapped_column(String(80), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CanvasConnection(Base):
    """A faculty member's authorization for CometIQ to read their Canvas courses. Tokens are encrypted at rest."""
    __tablename__ = "canvas_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    canvas_user_id: Mapped[str | None] = mapped_column(String(40))
    canvas_name: Mapped[str | None] = mapped_column(String(200))
    access_token: Mapped[str] = mapped_column(Text)          # encrypted
    refresh_token: Mapped[str | None] = mapped_column(Text)  # encrypted
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CourseAssignment(Base):
    """A graded assignment imported from Canvas, with the skills its instructions and rubric ask students to practice."""
    __tablename__ = "course_assignments"
    __table_args__ = (UniqueConstraint("syllabus_id", "canvas_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    syllabus_id: Mapped[str] = mapped_column(ForeignKey("syllabi.id", ondelete="CASCADE"), index=True)
    canvas_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(300))
    points: Mapped[float | None] = mapped_column(Float)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_types: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    rubric: Mapped[list] = mapped_column(JSON, default=list)      # [{"criterion", "points", "ratings": [...]}]
    skills: Mapped[list] = mapped_column(JSON, default=list)      # skill names found in the instructions or rubric
    graded: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CredentialBadgeClass(Base):
    """The Canvas Credentials badge class created for one skill at one level, reused for every student."""
    __tablename__ = "credential_badge_classes"
    __table_args__ = (UniqueConstraint("org_id", "skill_id", "level"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IdempotencyKey(Base):
    """A client-chosen key for a write request: a retried or double-clicked submission returns the first response instead
    of acting twice. Kept for a day."""
    __tablename__ = "idempotency_keys"
    __table_args__ = (CheckConstraint("status IN ('pending', 'done')", name="ck_idempotency_keys_status"),)
    key: Mapped[str] = mapped_column(String(120), primary_key=True)   # user id + client key
    user_id: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary)
    response_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class CacheVersion(Base):
    """Bumped whenever data that cached views depend on changes; part of every cache key (shared by all app instances)."""
    __tablename__ = "cache_versions"
    scope: Mapped[str] = mapped_column(String(40), primary_key=True)   # an organization id, or "*" for shared data such as job postings
    version: Mapped[int] = mapped_column(Integer, default=0)


# ── Indexes for foreign keys and common filters ─────────────────────────────────
# PostgreSQL does not index foreign keys automatically; these keep joins and ON DELETE actions fast.
from sqlalchemy import CheckConstraint, Index  # noqa: E402

_FK_INDEXES = [
    (CurriculumMapEntry, "set_by_id"), (CurriculumMapEntry, "skill_id"), (CurriculumMapEntry, "course_id"),
    (Evidence, "course_id"), (Evidence, "reviewer_id"), (JobSample, "created_by"), (PlanReview, "advisor_id"),
    (ProgramCore, "course_id"), (SkillBadge, "course_id"), (SkillBadge, "skill_id"), (SkillStack, "created_by"),
    (StudentCourse, "course_id"), (Syllabus, "course_id"), (ConcentrationCourse, "course_id"),
    (StudentProfile, "concentration_id"), (StudentProfile, "program_id"), (SyllabusSkill, "skill_id"), (SyllabusVersion, "created_by"),
    (GapAnalysis, "sample_id"), (GapAnalysis, "catalog_version_id"), (GapAnalysis, "syllabus_version_id"), (ForgeDraft, "analysis_id"),
    (GapReview, "skill_id"), (GapReview, "reviewer_id"), (CurriculumProposal, "forge_draft_id"), (CurriculumProposal, "author_id"),
    (CurriculumProposal, "base_version_id"), (GapDecision, "skill_id"), (GapDecision, "forge_draft_id"), (GapDecision, "reviewer_id"),
    (GapDecision, "analysis_id"), (ProposalComment, "author_id"), (ProposalReview, "reviewer_id"), (SponsoredProject, "decision_id"),
    (SponsoredProject, "forge_draft_id"), (SponsoredProject, "skill_id"), (CredentialBadgeClass, "skill_id"),
]
for _cls, _col in _FK_INDEXES:
    Index(f"ix_{_cls.__tablename__}_{_col}", getattr(_cls, _col))

Index("ix_jobs_open_family", Job.is_open, Job.role_family)
Index("ix_jobs_source_posted", Job.source, Job.posted_at)
Index("ix_gap_analyses_syllabus_created", GapAnalysis.syllabus_id, GapAnalysis.created_at)
Index("ix_evidence_student_status", Evidence.student_id, Evidence.status)
Index("ix_skill_badges_student_status", SkillBadge.student_id, SkillBadge.status)
Index("ix_gap_decisions_syllabus_status", GapDecision.syllabus_id, GapDecision.status)
Index("ix_student_courses_user_status", StudentCourse.user_id, StudentCourse.status)
Index("ix_users_org_role", User.org_id, User.role)
Index("ix_syllabi_org_code", Syllabus.org_id, Syllabus.code)
Index("ix_audit_log_org_created", AuditLog.org_id, AuditLog.created_at)
Index("ix_tasks_status_created", Task.status, Task.created_at)
_ACTIVE_DECISION = GapDecision.status.in_(("open", "drafted", "implemented"))
Index("uq_gap_decisions_one_active", GapDecision.syllabus_id, GapDecision.skill_id, unique=True,
      postgresql_where=_ACTIVE_DECISION, sqlite_where=_ACTIVE_DECISION)


# ── Value constraints: the database rejects values the application would never write ──
def _in(col: str, *values: str) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


_CHECKS = [
    (User, "role", _in("role", *ROLES)),
    (StudentCourse, "status", _in("status", "completed", "enrolled", "planned")),
    (JobSkill, "importance", _in("importance", "required", "preferred")),
    (CourseSkill, "weight", "weight >= 0"),
    (GapAnalysis, "score", "score >= 0 AND score <= 100"),
    (GapReview, "faculty_status", _in("faculty_status", "practiced", "mentioned_only", "not_covered", "not_relevant")),
    (GapReview, "decision", _in("decision", "confirmed", "corrected")),
    (GapReview, "action", _in("action", "none", "planned", "done")),
    (GapDecision, "decision", _in("decision", "add_here", "covered_elsewhere", "defer", "out_of_scope")),
    (GapDecision, "status", _in("status", "open", "drafted", "implemented", "superseded")),
    (CurriculumProposal, "status", _in("status", "draft", "in_review", "changes_requested", "approved", "adopted", "withdrawn")),
    (CurriculumProposal, "required_approvals", "required_approvals >= 1"),
    (ProposalReview, "vote", _in("vote", "approve", "request_changes")),
    (CurriculumMapEntry, "level", _in("level", "I", "P", "M", "-")),
    (SkillBadge, "level", _in("level", "practiced", "mastered")),
    (SkillBadge, "status", _in("status", "active", "revoked")),
    (Evidence, "kind", _in("kind", "course", "certification", "project", "experience")),
    (Evidence, "status", _in("status", "pending", "verified", "rejected")),
    (Evidence, "bonus_points", "bonus_points >= 0 AND bonus_points <= 20"),
    (Application, "status", _in("status", "applied", "shortlisted", "interview", "offer", "hired", "rejected")),
    (PlanReview, "status", _in("status", "submitted", "approved", "changes_requested")),
    (Task, "status", _in("status", "queued", "running", "done", "failed")),
    (SponsoredProject, "status", _in("status", "offered", "accepted", "declined", "completed", "withdrawn")),
    (SponsoredProject, "kind", _in("kind", "project", "dataset", "guest_session")),
    (JobSample, "kind", _in("kind", "documented", "auto")),
]
for _cls, _col, _sql in _CHECKS:
    _cls.__table__.append_constraint(CheckConstraint(_sql, name=f"ck_{_cls.__tablename__}_{_col}"))
