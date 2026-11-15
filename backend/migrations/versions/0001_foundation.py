"""Phase 0 foundation: settings, profile facts, LLM ledger, approvals, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

FACT_KINDS = "('professional', 'personal_project', 'learning', 'certification', 'education', 'publication', 'award')"
APPROVAL_STATUSES = "('pending', 'approved', 'edited', 'rejected')"


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "employment",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("title_on_resume", sa.String(200)),
        sa.Column("official_title", sa.String(200)),
        sa.Column("location", sa.String(200)),
        sa.Column("start", sa.String(7), nullable=False),
        sa.Column("end", sa.String(7)),
    )
    op.create_table(
        "profile_facts",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("employer_id", sa.String(50), sa.ForeignKey("employment.id")),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("skills", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("metric", sa.Text),
        sa.Column("needs_confirmation", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text),
        sa.Column("source_doc", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"kind IN {FACT_KINDS}", name="ck_profile_facts_kind"),
    )
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("engine", sa.String(30), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd_equiv", sa.Numeric(10, 5), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_llm_usage_at", "llm_usage", ["at"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("entity_ref", sa.String(200), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("thread_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN {APPROVAL_STATUSES}", name="ck_approvals_status"),
    )
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_ref", sa.String(200)),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    for table in ("audit_log", "approvals", "llm_usage", "profile_facts", "employment", "settings"):
        op.drop_table(table)
