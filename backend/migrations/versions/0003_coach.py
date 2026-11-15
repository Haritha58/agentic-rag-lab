"""Phase 5a: coach sessions and messages, proficiency, readiness breakdown.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=None if nullable else sa.func.now(), nullable=nullable)


def upgrade() -> None:
    op.add_column("job_scores", sa.Column("readiness_breakdown", JSONB))
    op.create_table(
        "coach_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("round_type", sa.String(30)),
        sa.Column("topic", sa.String(40)),
        sa.Column("interview_date", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        ts("started_at"),
        ts("ended_at", nullable=True),
        sa.Column("summary", JSONB),
        sa.Column("readiness_before", sa.Integer),
        sa.Column("readiness_after", sa.Integer),
        sa.CheckConstraint("mode IN ('learn', 'quiz', 'mock', 'readiness', 'story')", name="ck_coach_sessions_mode"),
    )
    op.create_table(
        "coach_messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("assessment", JSONB),
        ts("at"),
    )
    op.create_index("ix_coach_messages_session", "coach_messages", ["session_id", "id"])
    op.create_table(
        "proficiency_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("coach_sessions.id", ondelete="SET NULL")),
        sa.Column("message_id", sa.BigInteger, sa.ForeignKey("coach_messages.id", ondelete="SET NULL")),
        ts("at"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_proficiency_events_score"),
    )
    op.create_index("ix_proficiency_events_topic", "proficiency_events", ["topic"])
    op.create_table(
        "topic_self_ratings",
        sa.Column("topic", sa.String(40), primary_key=True),
        sa.Column("rating", sa.Integer, nullable=False),
        ts("updated_at"),
        sa.CheckConstraint("rating BETWEEN 0 AND 5", name="ck_topic_self_ratings_rating"),
    )


def downgrade() -> None:
    for table in ("topic_self_ratings", "proficiency_events", "coach_messages", "coach_sessions"):
        op.drop_table(table)
    op.drop_column("job_scores", "readiness_breakdown")
