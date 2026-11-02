"""Desktop sign-in (jumetra-frontend #62): devices, desktop_auth_codes, and which client and device a refresh token belongs to.

Revision ID: 0002_desktop_sign_in
Revises: 0001_baseline
Create Date: 2026-10-29 10:25:08.352753
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0002_desktop_sign_in'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('devices',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('app_version', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_devices_user_id'), ['user_id'], unique=False)

    op.create_table('desktop_auth_codes',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('code_challenge', sa.String(length=128), nullable=False),
    sa.Column('code_challenge_method', sa.String(length=8), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=True),
    sa.Column('redirect_uri', sa.String(length=256), nullable=False),
    sa.Column('device_name', sa.String(length=120), nullable=False),
    sa.Column('device_platform', sa.String(length=16), nullable=False),
    sa.Column('app_version', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('device_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exchanged_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    with op.batch_alter_table('desktop_auth_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_desktop_auth_codes_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('access_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('device_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_access_tokens_device_id'), ['device_id'], unique=False)
        batch_op.create_foreign_key('fk_access_tokens_device_id', 'devices', ['device_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client', sa.String(length=16), server_default='web', nullable=False))
        batch_op.add_column(sa.Column('device_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_refresh_tokens_device_id'), ['device_id'], unique=False)
        batch_op.create_foreign_key('fk_refresh_tokens_device_id', 'devices', ['device_id'], ['id'], ondelete='CASCADE')



def downgrade() -> None:
    with op.batch_alter_table('access_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('fk_access_tokens_device_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_access_tokens_device_id'))
        batch_op.drop_column('device_id')

    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('fk_refresh_tokens_device_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_device_id'))
        batch_op.drop_column('device_id')
        batch_op.drop_column('client')

    with op.batch_alter_table('desktop_auth_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_desktop_auth_codes_user_id'))

    op.drop_table('desktop_auth_codes')
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_devices_user_id'))

    op.drop_table('devices')
