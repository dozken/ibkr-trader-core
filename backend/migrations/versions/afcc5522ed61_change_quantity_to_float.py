"""change_quantity_to_float

Revision ID: afcc5522ed61
Revises: c3d4e5f6a7b8
Create Date: 2026-04-29 22:19:35.839551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afcc5522ed61'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('trade_history') as batch_op:
        batch_op.alter_column('quantity',
               existing_type=sa.Integer(),
               type_=sa.Float(),
               existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('trade_history') as batch_op:
        batch_op.alter_column('quantity',
               existing_type=sa.Float(),
               type_=sa.Integer(),
               existing_nullable=False)
