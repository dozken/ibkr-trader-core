import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ibkr_core.core.auth import require_api_key
from ibkr_core.core.database import get_db
from ibkr_core.core.models import Account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    label: str
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    ibkr_account_id: Optional[str] = None
    is_paper: bool = True
    read_only: bool = False


class AccountPatch(BaseModel):
    label: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None
    ibkr_account_id: Optional[str] = None
    is_paper: Optional[bool] = None
    is_active: Optional[bool] = None
    read_only: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    label: str
    host: str
    port: int
    client_id: int
    ibkr_account_id: Optional[str]
    is_paper: bool
    is_active: bool
    read_only: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[AccountResponse])
def list_accounts(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(Account)
    if not include_inactive:
        q = q.filter(Account.is_active.is_(True))
    return q.order_by(Account.id).all()


async def _apply_read_only(request: Request, acc: Account) -> None:
    """Push a read_only flip onto the live worker.

    execute_trade re-reads the flag from the DB per order, so the block itself is
    already in force. The worker still holds its old connection though, and a
    readonly IB connection cannot transmit orders at all — so it must reconnect
    in the new mode for an arm to actually reach IBKR.
    """
    am = getattr(request.app.state, "account_manager", None)
    if am is None:
        return
    w = am.get_worker_by_id(acc.id)
    if w is None:
        return

    siblings = [aid for aid in am.list_account_ids()
                if aid != acc.id and am.get_worker_by_id(aid) is not None
                and am.get_worker_by_id(aid).ib is w.ib]
    if siblings:
        logger.warning(
            "Account %s shares its IBKR connection with accounts %s — the "
            "read_only=%s mode change applies to all of them. Give them distinct "
            "client_ids to separate the modes.", acc.id, siblings, acc.read_only,
        )

    w.readonly = acc.read_only
    try:
        w.disconnect()
        ok = await w.connect()
        logger.info("Account %s reconnected read_only=%s (ok=%s)", acc.id, acc.read_only, ok)
    except Exception:
        logger.warning(
            "Account %s: reconnect after read_only=%s failed — the loop will retry",
            acc.id, acc.read_only, exc_info=True,
        )


@router.post("", response_model=AccountResponse, status_code=201,
             dependencies=[Depends(require_api_key)])
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    conflict = db.query(Account).filter(
        Account.client_id == body.client_id,
        Account.host == body.host,
        Account.port == body.port,
        Account.is_active.is_(True),
    ).first()
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Active account with client_id={body.client_id} already exists on {body.host}:{body.port}",
        )
    acc = Account(**body.model_dump())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@router.patch("/{account_id}", response_model=AccountResponse,
              dependencies=[Depends(require_api_key)])
async def patch_account(account_id: int, body: AccountPatch, request: Request,
                        db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    was_read_only = acc.read_only
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    if body.read_only is not None and body.read_only != was_read_only:
        await _apply_read_only(request, acc)
    return acc


@router.delete("/{account_id}", response_model=AccountResponse,
               dependencies=[Depends(require_api_key)])
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.is_active = False
    db.commit()
    db.refresh(acc)
    return acc
