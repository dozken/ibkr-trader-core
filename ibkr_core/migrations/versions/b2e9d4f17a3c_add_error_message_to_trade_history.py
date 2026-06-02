"""add error_message to trade_history

Revision ID: b2e9d4f17a3c
Revises: a1f7c2d83b90
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2e9d4f17a3c'
down_revision: Union[str, Sequence[str], None] = 'a1f7c2d83b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trade_history', sa.Column('error_message', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('trade_history', 'error_message')
