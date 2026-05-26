from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ibkr_core.core.database import get_db
from ibkr_core.core.models import Account

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
        q = q.filter(Account.is_active == True)
    return q.order_by(Account.id).all()


@router.post("", response_model=AccountResponse, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    conflict = db.query(Account).filter(
        Account.client_id == body.client_id,
        Account.host == body.host,
        Account.port == body.port,
        Account.is_active == True,
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


@router.patch("/{account_id}", response_model=AccountResponse)
def patch_account(account_id: int, body: AccountPatch, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete("/{account_id}", response_model=AccountResponse)
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.is_active = False
    db.commit()
    db.refresh(acc)
    return acc
