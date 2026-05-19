"""add_twap_executions_table

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-05-03 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'twap_executions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('symbol', sa.String(), nullable=False, index=True),
        sa.Column('slice_qty', sa.Float(), nullable=False),
        sa.Column('n_slices', sa.Integer(), nullable=False),
        sa.Column('slices_submitted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('interval_secs', sa.Integer(), nullable=False),
        sa.Column('stop_price', sa.Float(), nullable=True),
        sa.Column('tp_price', sa.Float(), nullable=True),
        sa.Column('trailing_amount', sa.Float(), nullable=True),
        sa.Column('exchange', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='RUNNING'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('twap_executions')
