"""add_account_id_to_pending_signals

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def upgrade() -> None:
    if not _has_column("pending_signals", "account_id"):
        op.add_column(
            "pending_signals",
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True, index=True),
        )


def downgrade() -> None:
    op.drop_column("pending_signals", "account_id")
