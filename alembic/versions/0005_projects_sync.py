"""Project sync (Phase Two sprint 11, DSK-14): synced_projects, synced_files, file_blobs, project_revisions.

Revision ID: 0005_projects_sync
Revises: 0004_consents
Create Date: 2026-11-02 16:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0005_projects_sync'
down_revision = '0004_consents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('synced_projects',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('board', sa.String(length=64), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', 'owner_id')
    )
    op.create_table('synced_files',
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('path', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', 'owner_id', 'path')
    )
    op.create_table('file_blobs',
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('owner_id', 'sha256')
    )
    op.create_table('project_revisions',
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('device', sa.String(length=120), nullable=False),
    sa.Column('files', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', 'owner_id', 'revision')
    )


def downgrade() -> None:
    op.drop_table('project_revisions')
    op.drop_table('file_blobs')
    op.drop_table('synced_files')
    op.drop_table('synced_projects')
