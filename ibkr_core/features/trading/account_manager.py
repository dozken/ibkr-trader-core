import logging
from typing import Dict, List, Optional, Tuple

from ibkr_core.core.database import SessionLocal
from ibkr_core.core.models import Account
from ibkr_core.features.trading.worker import IBKRWorker

logger = logging.getLogger(__name__)


class AccountManager:
    """
    Manages one IBKRWorker per active Account.
    Sub-accounts on the same gateway share a single IB connection
    but get separate workers with ibkr_account_id filtering.
    """

    def __init__(self) -> None:
        self._workers: Dict[int, IBKRWorker] = {}
        self._connections: Dict[Tuple[str, int, int], IBKRWorker] = {}

    def get_worker(self, account_id: int, host: str, port: int,
                   client_id: int, ibkr_account_id: str = "",
                   readonly: bool = False) -> IBKRWorker:
        if account_id in self._workers:
            return self._workers[account_id]

        conn_key = (host, port, client_id)
        if conn_key in self._connections:
            base = self._connections[conn_key]
            worker = IBKRWorker(host=host, port=port, client_id=client_id,
                                ibkr_account_id=ibkr_account_id or None,
                                readonly=readonly, account_id=account_id)
            worker.ib = base.ib
            logger.info(f"Created IBKRWorker for account {account_id} "
                        f"({host}:{port} cid={client_id} sub={ibkr_account_id}) "
                        f"sharing connection")
        else:
            worker = IBKRWorker(host=host, port=port, client_id=client_id,
                                ibkr_account_id=ibkr_account_id or None,
                                readonly=readonly, account_id=account_id)
            self._connections[conn_key] = worker
            logger.info(f"Created IBKRWorker for account {account_id} "
                        f"({host}:{port} cid={client_id} sub={ibkr_account_id})")

        self._workers[account_id] = worker
        return worker

    def get_worker_by_id(self, account_id: int) -> Optional[IBKRWorker]:
        return self._workers.get(account_id)

    def list_account_ids(self) -> List[int]:
        return list(self._workers.keys())

    def remove_worker(self, account_id: int) -> None:
        worker = self._workers.pop(account_id, None)
        if worker:
            still_used = any(w.ib is worker.ib for w in self._workers.values())
            if not still_used:
                worker.disconnect()
            logger.info(f"Removed IBKRWorker for account {account_id}")

    async def connect_all(self) -> Dict[int, bool]:
        results = {}
        connected_ibs = set()
        for account_id, worker in self._workers.items():
            ib_id = id(worker.ib)
            if ib_id in connected_ibs:
                results[account_id] = True
                continue
            try:
                ok = await worker.connect()
                results[account_id] = bool(ok)
                if ok:
                    connected_ibs.add(ib_id)
            except Exception as e:
                logger.error(f"connect_all failed for account {account_id}: {e}")
                results[account_id] = False
        return results

    def disconnect_all(self) -> None:
        disconnected = set()
        for account_id, worker in list(self._workers.items()):
            ib_id = id(worker.ib)
            if ib_id not in disconnected:
                try:
                    worker.disconnect()
                except Exception as e:
                    logger.warning(f"disconnect_all error for account {account_id}: {e}")
                disconnected.add(ib_id)
        self._workers.clear()
        self._connections.clear()

    @classmethod
    def from_db(cls) -> "AccountManager":
        """Load all active accounts from DB and pre-register workers."""
        mgr = cls()
        db = SessionLocal()
        try:
            accounts: List[Account] = db.query(Account).filter(Account.is_active.is_(True)).order_by(Account.id).all()
            for acc in accounts:
                mgr.get_worker(
                    account_id=acc.id,
                    host=acc.host,
                    port=acc.port,
                    client_id=acc.client_id,
                    ibkr_account_id=acc.ibkr_account_id or "",
                    readonly=acc.read_only,
                )
            logger.info(f"AccountManager loaded {len(accounts)} active account(s) from DB")
        finally:
            db.close()
        return mgr


_manager: Optional[AccountManager] = None


def get_account_manager() -> AccountManager:
    global _manager
    if _manager is None:
        _manager = AccountManager.from_db()
    return _manager
