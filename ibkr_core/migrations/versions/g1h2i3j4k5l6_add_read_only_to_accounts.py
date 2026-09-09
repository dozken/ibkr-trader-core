"""add_read_only_to_accounts

Revision ID: g1h2i3j4k5l6
Revises: f3a1c8d29e45
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'd7a2b9c41e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def upgrade() -> None:
    if not _has_column("accounts", "read_only"):
        op.add_column('accounts', sa.Column('read_only', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('accounts', 'read_only')
