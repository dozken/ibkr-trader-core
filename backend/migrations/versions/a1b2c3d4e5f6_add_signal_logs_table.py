"""add_signal_logs_table

Revision ID: a1b2c3d4e5f6
Revises: fcbf491abc02
Create Date: 2026-05-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'signal_logs' not in inspector.get_table_names():
        op.create_table(
            'signal_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('symbol', sa.String(), nullable=False),
            sa.Column('action', sa.String(), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=False),
            sa.Column('f_score', sa.Float(), nullable=True),
            sa.Column('t_score', sa.Float(), nullable=True),
            sa.Column('s_score', sa.Float(), nullable=True),
            sa.Column('signal_price', sa.Float(), nullable=True),
            sa.Column('outcome_7d_pct', sa.Float(), nullable=True),
            sa.Column('outcome_30d_pct', sa.Float(), nullable=True),
            sa.Column('outcome_checked_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_signal_logs_id', 'signal_logs', ['id'])
        op.create_index('ix_signal_logs_symbol', 'signal_logs', ['symbol'])


def downgrade() -> None:
    op.drop_index('ix_signal_logs_symbol', table_name='signal_logs')
    op.drop_index('ix_signal_logs_id', table_name='signal_logs')
    op.drop_table('signal_logs')
