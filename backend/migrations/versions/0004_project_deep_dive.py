"""Coach project deep-dive mode: sessions can point at a private study guide.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coach_sessions", sa.Column("project_doc", sa.String(120)))
    op.drop_constraint("ck_coach_sessions_mode", "coach_sessions")
    op.create_check_constraint(
        "ck_coach_sessions_mode", "coach_sessions", "mode IN ('learn', 'quiz', 'mock', 'readiness', 'story', 'project')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_coach_sessions_mode", "coach_sessions")
    op.create_check_constraint(
        "ck_coach_sessions_mode", "coach_sessions", "mode IN ('learn', 'quiz', 'mock', 'readiness', 'story')"
    )
    op.drop_column("coach_sessions", "project_doc")
