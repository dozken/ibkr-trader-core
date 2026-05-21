"""add_signal_price_and_dry_run_state

Revision ID: c3d4e5f6a7b8
Revises: b2e9f4a71c83
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2e9f4a71c83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('trade_history') as batch_op:
        batch_op.add_column(sa.Column('signal_price', sa.Float(), nullable=True))

    # PostgreSQL only: enum values must be added explicitly
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TYPE tradestate ADD VALUE IF NOT EXISTS 'DRY_RUN'")


def downgrade() -> None:
    with op.batch_alter_table('trade_history') as batch_op:
        batch_op.drop_column('signal_price')
    # Note: PostgreSQL enum values cannot be removed without dropping and recreating the type.
