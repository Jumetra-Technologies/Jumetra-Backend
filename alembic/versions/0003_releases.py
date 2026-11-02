"""Desktop releases (Phase Two sprint 5): releases and release_files, for GET /releases/latest.

Revision ID: 0003_releases
Revises: 0002_desktop_sign_in
Create Date: 2026-11-02 11:40:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0003_releases'
down_revision = '0002_desktop_sign_in'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('releases',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('minimum_version', sa.String(length=32), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel', 'version', name='uq_releases_channel_version')
    )
    with op.batch_alter_table('releases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_releases_channel'), ['channel'], unique=False)

    op.create_table('release_files',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('release_id', sa.String(length=32), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('arch', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('url', sa.String(length=512), nullable=False),
    sa.Column('sha512', sa.String(length=128), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['release_id'], ['releases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('release_id', 'platform', 'arch', 'kind', name='uq_release_files_target')
    )
    with op.batch_alter_table('release_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_release_files_release_id'), ['release_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('release_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_release_files_release_id'))
    op.drop_table('release_files')
    with op.batch_alter_table('releases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_releases_channel'))
    op.drop_table('releases')
