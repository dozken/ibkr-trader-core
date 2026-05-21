"""add_pending_signals_table

Revision ID: b3c4d5e6f7a8
Revises: fcbf491abc02
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'fcbf491abc02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pending_signals',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('symbol', sa.String(), nullable=False, index=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('reasoning', sa.String(), nullable=True),
        sa.Column('exchange', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('pending_signals')
