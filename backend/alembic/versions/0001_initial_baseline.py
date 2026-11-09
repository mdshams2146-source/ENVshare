"""Initial baseline schema

Revision ID: 0001_initial_baseline
Revises: 
Create Date: 2026-11-06 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '0001_initial_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('password_hash', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_users_email', 'users', ['email'], unique=True)

    if "projects" not in existing_tables:
        op.create_table(
            'projects',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if "project_members" not in existing_tables:
        op.create_table(
            'project_members',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('role', sa.String(), server_default='MEMBER'),
            sa.UniqueConstraint('user_id', 'project_id', name='uq_user_project')
        )

    if "environments" not in existing_tables:
        op.create_table(
            'environments',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('project_id', 'name', name='uq_project_env_name')
        )

    if "variables" not in existing_tables:
        op.create_table(
            'variables',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('key', sa.String(), nullable=False),
            sa.Column('value', sa.String(), nullable=False),
            sa.Column('iv', sa.String(), nullable=True),
            sa.Column('is_sensitive', sa.Boolean(), server_default=sa.false()),
            sa.Column('environment_id', sa.String(), sa.ForeignKey('environments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('environment_id', 'key', name='uq_env_var_key')
        )

    if "history_logs" not in existing_tables:
        op.create_table(
            'history_logs',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('action', sa.String(), nullable=False),
            sa.Column('key', sa.String(), nullable=True),
            sa.Column('old_value', sa.String(), nullable=True),
            sa.Column('new_value', sa.String(), nullable=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('environment_id', sa.String(), sa.ForeignKey('environments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if "project_invitations" not in existing_tables:
        op.create_table(
            'project_invitations',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('token', sa.String(), nullable=False),
            sa.Column('role', sa.String(), server_default='MEMBER'),
            sa.Column('is_used', sa.Boolean(), server_default=sa.false()),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_project_invitations_token', 'project_invitations', ['token'], unique=True)

    if "environment_snapshots" not in existing_tables:
        op.create_table(
            'environment_snapshots',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('environment_id', sa.String(), sa.ForeignKey('environments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_by_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('variables_data', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for tbl in [
        'environment_snapshots',
        'project_invitations',
        'history_logs',
        'variables',
        'environments',
        'project_members',
        'projects',
        'users'
    ]:
        if tbl in existing_tables:
            op.drop_table(tbl)

