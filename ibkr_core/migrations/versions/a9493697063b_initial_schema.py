"""initial_schema

Revision ID: a9493697063b
Revises:
Create Date: 2026-04-26 16:47:38.660445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9493697063b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('shariah_status', sa.String(), nullable=False),
        sa.Column('data_source', sa.String(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('business_activity', sa.String(), nullable=True),
        sa.Column('ibkr_order_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'])
    op.create_index('ix_audit_logs_symbol', 'audit_logs', ['symbol'])
    op.create_index('ix_audit_logs_ibkr_order_id', 'audit_logs', ['ibkr_order_id'])

    op.create_table(
        'purification_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('dividend_amount', sa.Float(), nullable=False),
        sa.Column('purification_amount', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('donation_receipt_link', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purification_history_id', 'purification_history', ['id'])
    op.create_index('ix_purification_history_symbol', 'purification_history', ['symbol'])

    op.create_table(
        'trade_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(), nullable=False),
        sa.Column('order_type', sa.String(), nullable=True),
        sa.Column('state', sa.Enum(
            'PENDING_COMPLIANCE', 'COMPLIANCE_APPROVED', 'COMPLIANCE_REJECTED',
            'SUBMITTED', 'FILLED', 'CANCELLED', 'IBKR_ERROR',
            'PENDING_SETTLEMENT', 'SETTLED',
            name='tradestate'
        ), nullable=False),
        sa.Column('ibkr_order_id', sa.Integer(), nullable=True),
        sa.Column('fill_price', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_trade_history_id', 'trade_history', ['id'])
    op.create_index('ix_trade_history_symbol', 'trade_history', ['symbol'])
    op.create_index('ix_trade_history_ibkr_order_id', 'trade_history', ['ibkr_order_id'])

    op.create_table(
        'position_compliance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('shariah_status', sa.String(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('is_active_holding', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_position_compliance_id', 'position_compliance', ['id'])
    op.create_index('ix_position_compliance_symbol', 'position_compliance', ['symbol'])


def downgrade() -> None:
    op.drop_index('ix_position_compliance_symbol', 'position_compliance')
    op.drop_index('ix_position_compliance_id', 'position_compliance')
    op.drop_table('position_compliance')

    op.drop_index('ix_trade_history_ibkr_order_id', 'trade_history')
    op.drop_index('ix_trade_history_symbol', 'trade_history')
    op.drop_index('ix_trade_history_id', 'trade_history')
    op.drop_table('trade_history')

    op.drop_index('ix_purification_history_symbol', 'purification_history')
    op.drop_index('ix_purification_history_id', 'purification_history')
    op.drop_table('purification_history')

    op.drop_index('ix_audit_logs_ibkr_order_id', 'audit_logs')
    op.drop_index('ix_audit_logs_symbol', 'audit_logs')
    op.drop_index('ix_audit_logs_id', 'audit_logs')
    op.drop_table('audit_logs')
