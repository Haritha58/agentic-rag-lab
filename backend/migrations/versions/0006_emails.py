"""Job-search emails found by the inbox check, linked to applications.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

CATEGORIES = (
    "application_confirmation", "recruiter_reply", "interview_invite", "assessment", "rejection", "offer", "other",
)


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("gmail_msg_id", sa.String(100), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(100)),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("sender", sa.String(300), nullable=False),
        sa.Column("subject", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("needs_reply", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("view_url", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"category IN {CATEGORIES}", name="ck_emails_category"),
    )
    op.create_index("ix_emails_application", "emails", ["application_id"])


def downgrade() -> None:
    op.drop_table("emails")
