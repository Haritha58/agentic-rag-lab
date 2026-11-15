"""Phase 2: companies, jobs, job sources, scores, discovery runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=None if nullable else sa.func.now(), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("key", sa.String(200), nullable=False, unique=True),
        sa.Column("ats", sa.String(30)),
        sa.Column("ats_slug", sa.String(100)),
        sa.Column("on_watchlist", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("category", sa.Integer),
        sa.Column("category_source", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("size_band", sa.String(30)),
        sa.Column("size_source", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("wlb_rating", sa.String(20), nullable=False, server_default="insufficient"),
        sa.Column("wlb_evidence", JSONB, nullable=False, server_default="[]"),
        sa.Column("stability", JSONB, nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text),
        sa.CheckConstraint("category IS NULL OR category IN (1, 2, 3)", name="ck_companies_category"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("apply_url", sa.Text),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("role_family", sa.String(30), nullable=False),
        sa.Column("seniority", sa.String(30)),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("location_raw", sa.Text),
        sa.Column("countries", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("cities", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("arrangement", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("segment", sa.String(30), nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default="{}"),
        sa.Column("exp_min", sa.Integer),
        sa.Column("exp_max", sa.Integer),
        sa.Column("salary", JSONB, nullable=False, server_default="{}"),
        sa.Column("skills", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        ts("posted_at", nullable=True),
        ts("first_seen_at"),
        ts("last_seen_at"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("user_status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.CheckConstraint(
            "segment IN ('IN_ONSITE_HYBRID', 'IN_REMOTE', 'INTL_REMOTE', 'INTL_RELOCATION', 'UNVERIFIED')",
            name="ck_jobs_segment",
        ),
        sa.CheckConstraint("status IN ('open', 'expired')", name="ck_jobs_status"),
        sa.CheckConstraint("user_status IN ('new', 'shortlisted', 'skipped')", name="ck_jobs_user_status"),
    )
    op.create_index("ix_jobs_segment_status", "jobs", ["segment", "status"])
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"])
    op.create_table(
        "job_sources",
        sa.Column("source", sa.String(30), primary_key=True),
        sa.Column("source_job_id", sa.String(200), primary_key=True),
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feed", sa.String(150), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        ts("last_seen_at"),
    )
    op.create_index("ix_job_sources_feed", "job_sources", ["feed"])
    op.create_table(
        "job_scores",
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        ts("scored_at"),
        sa.Column("method", sa.String(30), nullable=False, server_default="rules"),
        sa.Column("suitability", sa.Integer, nullable=False),
        sa.Column("suitability_breakdown", JSONB, nullable=False),
        sa.Column("opportunity", sa.Integer, nullable=False),
        sa.Column("opportunity_breakdown", JSONB, nullable=False),
        sa.Column("data_coverage", sa.Integer, nullable=False),
        sa.Column("readiness", sa.Integer),
        sa.Column("difficulty", sa.String(30), nullable=False),
        sa.Column("difficulty_evidence", JSONB, nullable=False, server_default="[]"),
        sa.Column("existing_skills", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("learning_skills", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("missing_skills", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("rejection_risks", JSONB, nullable=False, server_default="[]"),
        sa.Column("recommendation", sa.String(30), nullable=False),
    )
    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        ts("started_at"),
        ts("finished_at", nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("stats", JSONB, nullable=False, server_default="{}"),
        sa.Column("errors", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    for table in ("discovery_runs", "job_scores", "job_sources", "jobs", "companies"):
        op.drop_table(table)
