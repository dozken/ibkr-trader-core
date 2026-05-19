import asyncio
import logging
from typing import Dict, List, Optional

from backend.core.database import SessionLocal
from backend.core.models import Account
from backend.features.trading.worker import IBKRWorker

logger = logging.getLogger(__name__)


class AccountManager:
    """
    Manages one IBKRWorker per active Account.
    Workers are created lazily on first get_worker() call.
    """

    def __init__(self) -> None:
        self._workers: Dict[int, IBKRWorker] = {}

    def get_worker(self, account_id: int, host: str, port: int, client_id: int) -> IBKRWorker:
        if account_id not in self._workers:
            self._workers[account_id] = IBKRWorker(host=host, port=port, client_id=client_id)
            logger.info(f"Created IBKRWorker for account {account_id} ({host}:{port} cid={client_id})")
        return self._workers[account_id]

    def list_account_ids(self) -> List[int]:
        return list(self._workers.keys())

    def remove_worker(self, account_id: int) -> None:
        worker = self._workers.pop(account_id, None)
        if worker:
            worker.disconnect()
            logger.info(f"Removed IBKRWorker for account {account_id}")

    async def connect_all(self) -> Dict[int, bool]:
        results = {}
        for account_id, worker in self._workers.items():
            try:
                ok = await worker.connect()
                results[account_id] = bool(ok)
            except Exception as e:
                logger.error(f"connect_all failed for account {account_id}: {e}")
                results[account_id] = False
        return results

    def disconnect_all(self) -> None:
        for account_id, worker in list(self._workers.items()):
            try:
                worker.disconnect()
            except Exception as e:
                logger.warning(f"disconnect_all error for account {account_id}: {e}")
        self._workers.clear()

    @classmethod
    def from_db(cls) -> "AccountManager":
        """Load all active accounts from DB and pre-register workers."""
        mgr = cls()
        db = SessionLocal()
        try:
            accounts: List[Account] = db.query(Account).filter(Account.is_active == True).all()
            for acc in accounts:
                mgr.get_worker(
                    account_id=acc.id,
                    host=acc.host,
                    port=acc.port,
                    client_id=acc.client_id,
                )
            logger.info(f"AccountManager loaded {len(accounts)} active account(s) from DB")
        finally:
            db.close()
        return mgr


# Module-level singleton — initialized lazily on first import that calls it
_manager: Optional[AccountManager] = None


def get_account_manager() -> AccountManager:
    global _manager
    if _manager is None:
        _manager = AccountManager.from_db()
    return _manager
