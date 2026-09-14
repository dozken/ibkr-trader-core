"""add_rejected_concentration_state

Revision ID: e8f1a2b3c4d5
Revises: d7a2b9c41e08
Create Date: 2026-09-14 00:00:00.000000

TradeState.REJECTED_CONCENTRATION was added in 7d5765a (split from
REJECTED_FUNDS) without extending the PostgreSQL enum, so every
concentration-rejected BUY failed at INSERT with
"invalid input value for enum tradestate" and crashed the main-loop cycle.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e8f1a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'd7a2b9c41e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL only: enum values must be added explicitly. SQLite stores
    # the enum as VARCHAR and needs nothing.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute(
            "ALTER TYPE tradestate ADD VALUE IF NOT EXISTS 'REJECTED_CONCENTRATION'"
        )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed without dropping and
    # recreating the type; leave the value in place.
    pass
