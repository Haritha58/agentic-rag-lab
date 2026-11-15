"""Tables for each phase."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

FACT_KINDS = (
    "professional",
    "personal_project",
    "learning",
    "certification",
    "education",
    "publication",
    "award",
)
APPROVAL_STATUSES = ("pending", "approved", "edited", "rejected")


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Employment(Base):
    __tablename__ = "employment"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    company: Mapped[str] = mapped_column(String(200))
    title_on_resume: Mapped[str | None] = mapped_column(String(200))
    official_title: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    start: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    end: Mapped[str | None] = mapped_column(String(7))


class ProfileFact(Base):
    __tablename__ = "profile_facts"
    __table_args__ = (
        CheckConstraint(f"kind IN {FACT_KINDS}", name="ck_profile_facts_kind"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    employer_id: Mapped[str | None] = mapped_column(ForeignKey("employment.id"))
    text: Mapped[str] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    metric: Mapped[str | None] = mapped_column(Text)
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    source_doc: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    engine: Mapped[str] = mapped_column(String(30))
    task: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # On the Pro plan nothing is billed; this is the API-equivalent cost Claude Code reports.
    cost_usd_equiv: Mapped[Decimal] = mapped_column(Numeric(10, 5), default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(f"status IN {APPROVAL_STATUSES}", name="ck_approvals_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(50))
    entity_ref: Mapped[str] = mapped_column(String(200))
    payload: Mapped[Any] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    thread_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    entity_ref: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[Any] = mapped_column(JSONB, default=dict)


# ---------- Phase 2: discovery & matching ----------

SEGMENTS = ("IN_ONSITE_HYBRID", "IN_REMOTE", "INTL_REMOTE", "INTL_RELOCATION", "UNVERIFIED")
ARRANGEMENTS = (
    "onsite", "hybrid", "remote_occasional_office", "remote_city_restricted",
    "remote_first", "fully_remote", "unknown",
)
USER_STATUSES = ("new", "shortlisted", "skipped")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(200), unique=True)  # normalized name, for dedupe
    ats: Mapped[str | None] = mapped_column(String(30))
    ats_slug: Mapped[str | None] = mapped_column(String(100))
    on_watchlist: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[int | None] = mapped_column(Integer)  # 1 medium, 2 large, 3 highly competitive
    category_source: Mapped[str] = mapped_column(String(30), default="unknown")  # curated_estimate | user | unknown
    size_band: Mapped[str | None] = mapped_column(String(30))
    size_source: Mapped[str] = mapped_column(String(30), default="unknown")
    wlb_rating: Mapped[str] = mapped_column(String(20), default="insufficient")
    wlb_evidence: Mapped[Any] = mapped_column(JSONB, default=list)
    stability: Mapped[Any] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(Text)
    apply_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    role_family: Mapped[str] = mapped_column(String(30))
    seniority: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    location_raw: Mapped[str | None] = mapped_column(Text)
    countries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    cities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    arrangement: Mapped[str] = mapped_column(String(30), default="unknown")
    segment: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[Any] = mapped_column(JSONB, default=dict)  # quoted text behind each classification
    exp_min: Mapped[int | None] = mapped_column(Integer)
    exp_max: Mapped[int | None] = mapped_column(Integer)
    salary: Mapped[Any] = mapped_column(JSONB, default=dict)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | expired | ineligible (re-checked, location rules now rule it out)
    user_status: Mapped[str] = mapped_column(String(20), default="new")
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)


class JobSource(Base):
    """Every (source, id) a job was seen under, so the same job from two boards stays one row."""

    __tablename__ = "job_sources"

    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_job_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    feed: Mapped[str] = mapped_column(String(150))  # e.g. "greenhouse:stripe"; used for expiry
    url: Mapped[str] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobScore(Base):
    __tablename__ = "job_scores"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    method: Mapped[str] = mapped_column(String(30), default="rules")
    suitability: Mapped[int] = mapped_column(Integer)
    suitability_breakdown: Mapped[Any] = mapped_column(JSONB)
    opportunity: Mapped[int] = mapped_column(Integer)
    opportunity_breakdown: Mapped[Any] = mapped_column(JSONB)
    data_coverage: Mapped[int] = mapped_column(Integer)  # % of opportunity weight backed by real data
    readiness: Mapped[int | None] = mapped_column(Integer)  # set by interview prep (Phase 5)
    readiness_breakdown: Mapped[Any] = mapped_column(JSONB)
    difficulty: Mapped[str] = mapped_column(String(30))
    difficulty_evidence: Mapped[Any] = mapped_column(JSONB, default=list)
    existing_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    learning_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    missing_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    rejection_risks: Mapped[Any] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str] = mapped_column(String(30))


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | failed
    stats: Mapped[Any] = mapped_column(JSONB, default=dict)
    errors: Mapped[Any] = mapped_column(JSONB, default=list)


# ---------- Phase 5a: interview prep and coach ----------

COACH_MODES = ("learn", "quiz", "mock", "readiness", "story", "project")


class CoachSession(Base):
    __tablename__ = "coach_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(20))
    round_type: Mapped[str | None] = mapped_column(String(30))  # mock rounds only
    topic: Mapped[str | None] = mapped_column(String(40))  # learn/quiz focus, optional
    project_doc: Mapped[str | None] = mapped_column(String(120))  # project mode: file in data/interview_prep
    interview_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | ended
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[Any] = mapped_column(JSONB)
    readiness_before: Mapped[int | None] = mapped_column(Integer)
    readiness_after: Mapped[int | None] = mapped_column(Integer)


class CoachMessage(Base):
    __tablename__ = "coach_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("coach_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))  # user | coach
    content: Mapped[str] = mapped_column(Text)
    assessment: Mapped[Any] = mapped_column(JSONB)  # rubric for the user's previous answer
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProficiencyEvent(Base):
    """One scored answer on one topic. Proficiency is a time-decayed average of these."""

    __tablename__ = "proficiency_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(40))
    score: Mapped[int] = mapped_column(Integer)  # 0-100
    session_id: Mapped[int | None] = mapped_column(ForeignKey("coach_sessions.id", ondelete="SET NULL"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("coach_messages.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicSelfRating(Base):
    __tablename__ = "topic_self_ratings"

    topic: Mapped[str] = mapped_column(String(40), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer)  # 0-5
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------- Application tracking ----------

APPLICATION_STATUSES = (
    "applied", "viewed", "screening", "interviewing", "offer", "accepted", "rejected", "withdrawn", "no_response",
)
ROUND_STATUSES = ("scheduled", "completed", "cleared", "not_cleared", "cancelled")
EVIDENCE_TYPES = ("user_action", "email", "portal_page")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(f"status IN {APPLICATION_STATUSES}", name="ck_applications_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Unique: one application per job. Null for roles found outside JobPilot (referrals, recruiter outreach).
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), unique=True)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(30), default="company_site")
    resume_version: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="applied")
    applied_at: Mapped[date] = mapped_column(Date)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterviewRound(Base):
    __tablename__ = "interview_rounds"
    __table_args__ = (
        CheckConstraint(f"status IN {ROUND_STATUSES}", name="ck_interview_rounds_status"),
        CheckConstraint("self_rating BETWEEN 1 AND 5", name="ck_interview_rounds_self_rating"),
        UniqueConstraint("application_id", "round_no", name="uq_interview_rounds_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    round_no: Mapped[int] = mapped_column(Integer)
    round_type: Mapped[str] = mapped_column(String(30))
    label: Mapped[str | None] = mapped_column(String(200))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str | None] = mapped_column(String(20))  # video | phone | onsite
    interviewer: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    questions: Mapped[str | None] = mapped_column(Text)  # what they asked, for future prep
    feedback: Mapped[str | None] = mapped_column(Text)
    self_rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatusEvent(Base):
    """Every application status change, with the evidence behind it."""

    __tablename__ = "status_events"
    __table_args__ = (
        CheckConstraint(f"evidence_type IN {EVIDENCE_TYPES}", name="ck_status_events_evidence_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    evidence_type: Mapped[str] = mapped_column(String(20), default="user_action")
    evidence_ref: Mapped[str | None] = mapped_column(String(200))  # e.g. a Gmail message id
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


EMAIL_CATEGORIES = (
    "application_confirmation", "recruiter_reply", "interview_invite", "assessment",
    "rejection", "offer", "other",
)


class Email(Base):
    """A job-search email the inbox check has handled, so it's never processed twice."""

    __tablename__ = "emails"
    __table_args__ = (
        CheckConstraint(f"category IN {EMAIL_CATEGORIES}", name="ck_emails_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gmail_msg_id: Mapped[str] = mapped_column(String(100), unique=True)
    thread_id: Mapped[str | None] = mapped_column(String(100))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(30))
    sender: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    needs_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    view_url: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled: Mapped[bool] = mapped_column(Boolean, default=False)  # you dismissed it or replied
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
