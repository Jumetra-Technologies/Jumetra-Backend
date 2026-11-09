"""Consent to usage counting (consents.usage); crash_reports may now be unanswered.

A person can answer one question without the other: the website asks about
usage counting, the desktop app about crash reports. NULL means not asked.

Revision ID: 0007_usage_consent
Revises: 0006_activity_admin
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_usage_consent"
down_revision = "0006_activity_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("consents") as batch:
        batch.add_column(sa.Column("usage", sa.Boolean(), nullable=True))
        batch.alter_column("crash_reports", existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE consents SET crash_reports = false WHERE crash_reports IS NULL")
    with op.batch_alter_table("consents") as batch:
        batch.alter_column("crash_reports", existing_type=sa.Boolean(), nullable=False)
        batch.drop_column("usage")
