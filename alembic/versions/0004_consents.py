"""Crash-report consent (Phase Two sprint 6, DSK-81): consents and crash_reports.

Revision ID: 0004_consents
Revises: 0003_releases
Create Date: 2026-11-02 12:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0004_consents'
down_revision = '0003_releases'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('consents',
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('crash_reports', sa.Boolean(), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_in', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('crash_reports',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('install_id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('app_version', sa.String(length=32), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('arch', sa.String(length=16), nullable=False),
    sa.Column('process', sa.String(length=16), nullable=False),
    sa.Column('message', sa.String(length=2000), nullable=False),
    sa.Column('stack', sa.Text(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('crash_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crash_reports_install_id'), ['install_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crash_reports_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crash_reports_received_at'), ['received_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('crash_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_crash_reports_received_at'))
        batch_op.drop_index(batch_op.f('ix_crash_reports_user_id'))
        batch_op.drop_index(batch_op.f('ix_crash_reports_install_id'))
    op.drop_table('crash_reports')
    op.drop_table('consents')
