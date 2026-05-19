"""add_audit_log_hash_chain_columns

Revision ID: b2e9f4a71c83
Revises: f3a1c8d29e45
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2e9f4a71c83'
down_revision: Union[str, Sequence[str], None] = 'f3a1c8d29e45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.add_column(sa.Column('hash', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('previous_hash', sa.String(), nullable=True))
    op.create_index('ix_audit_logs_hash', 'audit_logs', ['hash'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_hash', table_name='audit_logs')
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.drop_column('previous_hash')
        batch_op.drop_column('hash')
