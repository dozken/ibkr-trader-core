"""add_accounts_table_and_account_id_fks

Revision ID: fcbf491abc02
Revises: afcc5522ed61
Create Date: 2026-05-01 00:05:23.067066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'fcbf491abc02'
down_revision: Union[str, Sequence[str], None] = 'afcc5522ed61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in inspect(bind).get_columns(table)]


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return inspect(bind).has_table(table)


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    return any(i["name"] == index for i in inspect(bind).get_indexes(table))


def upgrade() -> None:
    # accounts table
    if not _has_table("accounts"):
        op.create_table('accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(), nullable=False),
            sa.Column('ibkr_account_id', sa.String(), nullable=True),
            sa.Column('host', sa.String(), nullable=False),
            sa.Column('port', sa.Integer(), nullable=False),
            sa.Column('client_id', sa.Integer(), nullable=False),
            sa.Column('is_paper', sa.Boolean(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _has_index("accounts", "ix_accounts_ibkr_account_id"):
        op.create_index('ix_accounts_ibkr_account_id', 'accounts', ['ibkr_account_id'], unique=False)
    if not _has_index("accounts", "ix_accounts_id"):
        op.create_index('ix_accounts_id', 'accounts', ['id'], unique=False)

    # audit_logs
    if not _has_column("audit_logs", "account_id"):
        op.add_column('audit_logs', sa.Column('account_id', sa.Integer(), nullable=True))
    if not _has_index("audit_logs", "ix_audit_logs_account_id"):
        op.create_index('ix_audit_logs_account_id', 'audit_logs', ['account_id'], unique=False)

    # portfolio_snapshots
    if not _has_column("portfolio_snapshots", "account_id"):
        op.add_column('portfolio_snapshots', sa.Column('account_id', sa.Integer(), nullable=True))
    if not _has_index("portfolio_snapshots", "ix_portfolio_snapshots_account_id"):
        op.create_index('ix_portfolio_snapshots_account_id', 'portfolio_snapshots', ['account_id'], unique=False)

    # position_compliance
    if not _has_column("position_compliance", "account_id"):
        op.add_column('position_compliance', sa.Column('account_id', sa.Integer(), nullable=True))
    if not _has_index("position_compliance", "ix_position_compliance_account_id"):
        op.create_index('ix_position_compliance_account_id', 'position_compliance', ['account_id'], unique=False)

    # trade_history
    if not _has_column("trade_history", "account_id"):
        op.add_column('trade_history', sa.Column('account_id', sa.Integer(), nullable=True))
    if not _has_index("trade_history", "ix_trade_history_account_id"):
        op.create_index('ix_trade_history_account_id', 'trade_history', ['account_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_trade_history_account_id', table_name='trade_history')
    op.drop_column('trade_history', 'account_id')
    op.drop_index('ix_position_compliance_account_id', table_name='position_compliance')
    op.drop_column('position_compliance', 'account_id')
    op.drop_index('ix_portfolio_snapshots_account_id', table_name='portfolio_snapshots')
    op.drop_column('portfolio_snapshots', 'account_id')
    op.drop_index('ix_audit_logs_account_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'account_id')
    op.drop_index('ix_accounts_id', table_name='accounts')
    op.drop_index('ix_accounts_ibkr_account_id', table_name='accounts')
    op.drop_table('accounts')
