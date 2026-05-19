"""add_feature_snapshots_table

Revision ID: f3a1c8d29e45
Revises: e7626039f371
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a1c8d29e45'
down_revision: Union[str, Sequence[str], None] = 'e7626039f371'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'feature_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feature_snapshots_id', 'feature_snapshots', ['id'])
    op.create_index('ix_feature_snapshots_timestamp', 'feature_snapshots', ['timestamp'])
    op.create_index('ix_feature_snapshots_symbol', 'feature_snapshots', ['symbol'])


def downgrade() -> None:
    op.drop_index('ix_feature_snapshots_symbol', table_name='feature_snapshots')
    op.drop_index('ix_feature_snapshots_timestamp', table_name='feature_snapshots')
    op.drop_index('ix_feature_snapshots_id', table_name='feature_snapshots')
    op.drop_table('feature_snapshots')
