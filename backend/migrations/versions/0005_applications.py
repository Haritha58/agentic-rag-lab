"""Application tracking: applications, any number of interview rounds, status history.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APPLICATION_STATUSES = (
    "applied", "viewed", "screening", "interviewing", "offer", "accepted", "rejected", "withdrawn", "no_response",
)
ROUND_STATUSES = ("scheduled", "completed", "cleared", "not_cleared", "cancelled")


def ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="SET NULL"), unique=True),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("channel", sa.String(30), nullable=False, server_default="company_site"),
        sa.Column("resume_version", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="applied"),
        sa.Column("applied_at", sa.Date, nullable=False),
        sa.Column("follow_up_on", sa.Date),
        sa.Column("notes", sa.Text),
        ts("created_at"),
        ts("updated_at"),
        sa.CheckConstraint(f"status IN {APPLICATION_STATUSES}", name="ck_applications_status"),
    )
    op.create_table(
        "interview_rounds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_no", sa.Integer, nullable=False),
        sa.Column("round_type", sa.String(30), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("mode", sa.String(20)),
        sa.Column("interviewer", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("questions", sa.Text),
        sa.Column("feedback", sa.Text),
        sa.Column("self_rating", sa.Integer),
        ts("created_at"),
        sa.CheckConstraint(f"status IN {ROUND_STATUSES}", name="ck_interview_rounds_status"),
        sa.CheckConstraint("self_rating BETWEEN 1 AND 5", name="ck_interview_rounds_self_rating"),
        sa.UniqueConstraint("application_id", "round_no", name="uq_interview_rounds_no"),
    )
    op.create_table(
        "status_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("evidence_type", sa.String(20), nullable=False, server_default="user_action"),
        sa.Column("evidence_ref", sa.String(200)),
        sa.Column("note", sa.Text),
        ts("at"),
        sa.CheckConstraint("evidence_type IN ('user_action', 'email', 'portal_page')", name="ck_status_events_evidence_type"),
    )
    op.create_index("ix_status_events_application", "status_events", ["application_id", "id"])


def downgrade() -> None:
    for table in ("status_events", "interview_rounds", "applications"):
        op.drop_table(table)
