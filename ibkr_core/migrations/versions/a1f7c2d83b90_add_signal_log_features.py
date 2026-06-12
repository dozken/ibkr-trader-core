"""add features column to signal_logs

Revision ID: a1f7c2d83b90
Revises: d4e5f6a7b8c9
Create Date: 2026-05-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f7c2d83b90'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('signal_logs', sa.Column('features', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('signal_logs', 'features')
