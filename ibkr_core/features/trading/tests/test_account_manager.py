"""Tests for AccountManager — multi-account IBKR worker management."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ibkr_core.core.models import Base, Account
from ibkr_core.features.trading.account_manager import AccountManager


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _account(db, label="Paper", host="127.0.0.1", port=7497, client_id=1,
              ibkr_account_id="DU123", is_paper=True, is_active=True):
    acc = Account(
        label=label, host=host, port=port, client_id=client_id,
        ibkr_account_id=ibkr_account_id, is_paper=is_paper, is_active=is_active,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


# --- AccountManager basics ---

def test_get_worker_creates_worker_on_first_call():
    mgr = AccountManager()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker") as MockWorker:
        worker = mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        MockWorker.assert_called_once_with(
            host="127.0.0.1", port=7497, client_id=1,
            ibkr_account_id=None, readonly=False,
        )
        assert worker is MockWorker.return_value


def test_get_worker_returns_same_instance_on_second_call():
    mgr = AccountManager()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker") as MockWorker:
        w1 = mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        w2 = mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        assert MockWorker.call_count == 1
        assert w1 is w2


def test_get_worker_different_accounts_different_instances():
    mgr = AccountManager()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker") as MockWorker:
        MockWorker.side_effect = [MagicMock(), MagicMock()]
        w1 = mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        w2 = mgr.get_worker(account_id=2, host="127.0.0.1", port=7496, client_id=2)
        assert w1 is not w2
        assert MockWorker.call_count == 2


def test_list_account_ids_empty_initially():
    mgr = AccountManager()
    assert mgr.list_account_ids() == []


def test_list_account_ids_after_get_worker():
    mgr = AccountManager()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker"):
        mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        mgr.get_worker(account_id=2, host="127.0.0.1", port=7496, client_id=2)
    assert sorted(mgr.list_account_ids()) == [1, 2]


def test_remove_worker_disconnects_and_removes():
    mgr = AccountManager()
    mock_worker = MagicMock()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker", return_value=mock_worker):
        mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
    mgr.remove_worker(account_id=1)
    mock_worker.disconnect.assert_called_once()
    assert 1 not in mgr.list_account_ids()


def test_remove_nonexistent_worker_is_noop():
    mgr = AccountManager()
    mgr.remove_worker(account_id=99)  # should not raise


# --- from_db ---

def test_from_db_loads_active_accounts(db):
    _account(db, label="Paper", port=7497, client_id=1, is_active=True)
    _account(db, label="Live", port=7496, client_id=2, is_active=True)
    _account(db, label="Inactive", port=7499, client_id=3, is_active=False)

    with patch("ibkr_core.features.trading.account_manager.IBKRWorker") as MockWorker:
        MockWorker.side_effect = [MagicMock(), MagicMock()]
        with patch("ibkr_core.features.trading.account_manager.SessionLocal", return_value=db):
            mgr = AccountManager.from_db()

    assert len(mgr.list_account_ids()) == 2  # inactive excluded


def test_from_db_skips_inactive(db):
    _account(db, label="Inactive", is_active=False)
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker"):
        with patch("ibkr_core.features.trading.account_manager.SessionLocal", return_value=db):
            mgr = AccountManager.from_db()
    assert mgr.list_account_ids() == []


# --- connect_all / disconnect_all ---

@pytest.mark.asyncio
async def test_connect_all_calls_connect_on_each_worker():
    mgr = AccountManager()
    w1, w2 = MagicMock(), MagicMock()
    w1.connect = AsyncMock(return_value=True)
    w2.connect = AsyncMock(return_value=True)

    with patch("ibkr_core.features.trading.account_manager.IBKRWorker", side_effect=[w1, w2]):
        mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        mgr.get_worker(account_id=2, host="127.0.0.1", port=7496, client_id=2)

    results = await mgr.connect_all()
    w1.connect.assert_called_once()
    w2.connect.assert_called_once()
    assert results == {1: True, 2: True}


@pytest.mark.asyncio
async def test_connect_all_returns_false_on_failure():
    mgr = AccountManager()
    w1 = MagicMock()
    w1.connect = AsyncMock(return_value=False)

    with patch("ibkr_core.features.trading.account_manager.IBKRWorker", return_value=w1):
        mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)

    results = await mgr.connect_all()
    assert results == {1: False}


def test_disconnect_all_calls_disconnect_on_each():
    mgr = AccountManager()
    w1, w2 = MagicMock(), MagicMock()
    with patch("ibkr_core.features.trading.account_manager.IBKRWorker", side_effect=[w1, w2]):
        mgr.get_worker(account_id=1, host="127.0.0.1", port=7497, client_id=1)
        mgr.get_worker(account_id=2, host="127.0.0.1", port=7496, client_id=2)
    mgr.disconnect_all()
    w1.disconnect.assert_called_once()
    w2.disconnect.assert_called_once()
