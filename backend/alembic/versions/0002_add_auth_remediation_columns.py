"""Add auth remediation columns to users table

Revision ID: 0002_add_auth_columns
Revises: 0001_initial_baseline
Create Date: 2026-11-06 23:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '0002_add_auth_columns'
down_revision: Union[str, None] = '0001_initial_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('users')}

    if 'token_version' not in existing_cols:
        op.add_column(
            'users',
            sa.Column('token_version', sa.Integer(), nullable=False, server_default='1')
        )
    if 'reset_token_hash' not in existing_cols:
        op.add_column(
            'users',
            sa.Column('reset_token_hash', sa.String(), nullable=True)
        )
    if 'reset_token_expires_at' not in existing_cols:
        op.add_column(
            'users',
            sa.Column('reset_token_expires_at', sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('users')}

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'reset_token_expires_at' in existing_cols:
            batch_op.drop_column('reset_token_expires_at')
        if 'reset_token_hash' in existing_cols:
            batch_op.drop_column('reset_token_hash')
        if 'token_version' in existing_cols:
            batch_op.drop_column('token_version')
