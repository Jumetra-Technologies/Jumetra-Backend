"""Baseline: every table the server had before migrations (Phase One platform tables, the identity tables from the Firebase sign-in work, and the account data tables).

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-10-29 10:25:02.738096
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


# Columns a users table created by the September code lacks.
_USER_COLUMNS = (
    ("firebase_uid", sa.String(length=128)),
    ("photo_url", sa.String(length=512)),
    ("last_login_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    """Create what's missing. A database made by the old create_all path keeps its tables and data."""
    if not _has('organizations'):
        op.create_table('organizations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
        )
    if not _has('users'):
        op.create_table('users',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('organization_id', sa.String(length=32), nullable=False),
        sa.Column('firebase_uid', sa.String(length=128), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('firebase_uid')
        )
    if not _has('access_tokens'):
        op.create_table('access_tokens',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jti')
        )
        with op.batch_alter_table('access_tokens', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_access_tokens_user_id'), ['user_id'], unique=False)
    if not _has('lab_sessions'):
        op.create_table('lab_sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('owner_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('client_updated_at', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', 'owner_id')
        )
    if not _has('login_sessions'):
        op.create_table('login_sessions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('login_sessions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_login_sessions_user_id'), ['user_id'], unique=False)
    if not _has('oauth_accounts'):
        op.create_table('oauth_accounts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('provider_user_id', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_provider_user')
        )
        with op.batch_alter_table('oauth_accounts', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_oauth_accounts_user_id'), ['user_id'], unique=False)
    if not _has('projects'):
        op.create_table('projects',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _has('refresh_tokens'):
        op.create_table('refresh_tokens',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
        )
        with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)
    if not _has('user_profiles'):
        op.create_table('user_profiles',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('auth_provider', sa.String(length=32), nullable=True),
        sa.Column('self_role', sa.String(length=32), nullable=True),
        sa.Column('role_other', sa.String(length=80), nullable=True),
        sa.Column('organization', sa.String(length=120), nullable=True),
        sa.Column('location', sa.String(length=80), nullable=True),
        sa.Column('bio', sa.String(length=280), nullable=True),
        sa.Column('learning_progress', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
        )
    if not _has('user_projects'):
        op.create_table('user_projects',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('objectives', sa.Text(), nullable=False),
        sa.Column('contributors', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('hardware', sa.JSON(), nullable=False),
        sa.Column('teammates', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('user_projects', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_user_projects_owner_id'), ['owner_id'], unique=False)
    if not _has('websocket_tickets'):
        op.create_table('websocket_tickets',
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('jti')
        )
        with op.batch_alter_table('websocket_tickets', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_websocket_tickets_user_id'), ['user_id'], unique=False)
    if not _has('cookie_sessions'):
        op.create_table('cookie_sessions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('login_session_id', sa.String(length=32), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['login_session_id'], ['login_sessions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('cookie_sessions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_cookie_sessions_user_id'), ['user_id'], unique=False)
    if not _has('platform_experiments'):
        op.create_table('platform_experiments',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('external_id', sa.String(length=32), nullable=True),
        sa.Column('strategy', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('platform_experiments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_platform_experiments_external_id'), ['external_id'], unique=False)
    if not _has('user_project_experiments'):
        op.create_table('user_project_experiments',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('hardware', sa.JSON(), nullable=False),
        sa.Column('procedure', sa.Text(), nullable=False),
        sa.Column('observations', sa.Text(), nullable=False),
        sa.Column('results', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['user_projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('user_project_experiments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_user_project_experiments_project_id'), ['project_id'], unique=False)

    if _has('users'):
        existing = _columns('users')
        with op.batch_alter_table('users', schema=None) as batch_op:
            for name, kind in _USER_COLUMNS:
                if name not in existing:
                    batch_op.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_project_experiments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_project_experiments_project_id'))

    op.drop_table('user_project_experiments')
    with op.batch_alter_table('platform_experiments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_platform_experiments_external_id'))

    op.drop_table('platform_experiments')
    with op.batch_alter_table('cookie_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cookie_sessions_user_id'))

    op.drop_table('cookie_sessions')
    with op.batch_alter_table('websocket_tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_websocket_tickets_user_id'))

    op.drop_table('websocket_tickets')
    with op.batch_alter_table('user_projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_projects_owner_id'))

    op.drop_table('user_projects')
    op.drop_table('user_profiles')
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_user_id'))

    op.drop_table('refresh_tokens')
    op.drop_table('projects')
    with op.batch_alter_table('oauth_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_oauth_accounts_user_id'))

    op.drop_table('oauth_accounts')
    with op.batch_alter_table('login_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_sessions_user_id'))

    op.drop_table('login_sessions')
    op.drop_table('lab_sessions')
    with op.batch_alter_table('access_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_access_tokens_user_id'))

    op.drop_table('access_tokens')
    op.drop_table('users')
    op.drop_table('organizations')
