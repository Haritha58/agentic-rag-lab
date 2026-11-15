"""Jobs can become ineligible when a later run's location rules rule them out.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_status", "jobs", "status IN ('open', 'expired', 'ineligible')")


def downgrade() -> None:
    op.execute("UPDATE jobs SET status = 'expired' WHERE status = 'ineligible'")
    op.drop_constraint("ck_jobs_status", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_status", "jobs", "status IN ('open', 'expired')")
