"""add benchmark return columns to signal_logs

SPY return over the same forward window as each outcome, so labels can be
market-relative (alpha) instead of raw (beta).

Revision ID: d7a2b9c41e08
Revises: b2e9d4f17a3c
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7a2b9c41e08'
down_revision: Union[str, Sequence[str], None] = 'b2e9d4f17a3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('signal_logs', sa.Column('benchmark_7d_pct', sa.Float(), nullable=True))
    op.add_column('signal_logs', sa.Column('benchmark_30d_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_logs', 'benchmark_30d_pct')
    op.drop_column('signal_logs', 'benchmark_7d_pct')
