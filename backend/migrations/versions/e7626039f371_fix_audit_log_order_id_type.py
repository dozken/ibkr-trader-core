"""fix_audit_log_order_id_type

Revision ID: e7626039f371
Revises: a9493697063b
Create Date: 2026-04-26 16:49:03.744644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7626039f371'
down_revision: Union[str, Sequence[str], None] = 'a9493697063b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for column type changes (no ALTER COLUMN support)
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.alter_column(
            'ibkr_order_id',
            existing_type=sa.String(),
            type_=sa.Integer(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.alter_column(
            'ibkr_order_id',
            existing_type=sa.Integer(),
            type_=sa.String(),
            existing_nullable=True,
        )
