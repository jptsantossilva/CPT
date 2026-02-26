import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import get_session
from ..models import Account
from ..wallet_chains import (
    encode_wallet_identifier,
    is_bitcoin_address,
    is_solana_address,
    normalize_wallet_chain,
    parse_wallet_identifier,
)

router = APIRouter(prefix="/admin/wallets", tags=["admin"])
log = logging.getLogger(__name__)


class CreateWallet(BaseModel):
    identifier: str  # wallet address
    wallet_type: str | None = None  # auto|ethereum|bitcoin|solana
    label: str | None = None


class UpdateWallet(BaseModel):
    identifier: str | None = None
    wallet_type: str | None = None  # auto|ethereum|bitcoin|solana
    label: str | None = None


@router.post("/")
def create_wallet(payload: CreateWallet):
    try:
        raw_identifier = (payload.identifier or "").strip()
        raw_type = (payload.wallet_type or "").strip().lower()
        if raw_type and raw_type != "auto":
            chain = normalize_wallet_chain(raw_type)
            if chain not in {"ethereum", "bitcoin", "solana"}:
                raise HTTPException(status_code=400, detail="wallet_type must be auto, ethereum, bitcoin or solana")
            wallet_identifier = raw_identifier
            if chain == "bitcoin" and not is_bitcoin_address(wallet_identifier):
                raise HTTPException(status_code=400, detail="invalid bitcoin wallet address")
            if chain == "solana" and not is_solana_address(wallet_identifier):
                raise HTTPException(status_code=400, detail="invalid solana wallet address")
        else:
            chain, wallet_identifier = parse_wallet_identifier(raw_identifier)
        if not wallet_identifier:
            raise HTTPException(status_code=400, detail="identifier cannot be empty")
        with get_session() as s:
            a = Account(
                provider="wallet",
                identifier=encode_wallet_identifier(wallet_identifier, chain),
                label=payload.label,
                is_exchange=False,
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            return {
                "id": a.id,
                "identifier": wallet_identifier,
                "label": a.label,
                "wallet_type": chain,
            }
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to create wallet")
        raise HTTPException(status_code=500, detail="failed to create wallet")


@router.get("/")
def list_wallets():
    try:
        with get_session() as s:
            rows = s.query(Account).filter(Account.provider == "wallet").all()
            out = []
            for r in rows:
                chain, wallet_identifier = parse_wallet_identifier(r.identifier)
                out.append(
                    {
                        "id": r.id,
                        "identifier": wallet_identifier,
                        "label": r.label,
                        "wallet_type": chain,
                    }
                )
            return out
    except Exception:
        log.exception("failed to list wallets")
        raise HTTPException(status_code=500, detail="failed to list wallets")


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: int):
    try:
        with get_session() as s:
            a = s.get(Account, wallet_id)
            if not a:
                raise HTTPException(status_code=404, detail="not found")
            s.delete(a)
            s.commit()
            return {"deleted": wallet_id}
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to delete wallet id=%s", wallet_id)
        raise HTTPException(status_code=500, detail="failed to delete wallet")


@router.put("/{wallet_id}")
def update_wallet(wallet_id: int, payload: UpdateWallet):
    try:
        with get_session() as s:
            a = s.get(Account, wallet_id)
            if not a or a.provider != "wallet":
                raise HTTPException(status_code=404, detail="not found")

            next_identifier = a.identifier

            if payload.identifier is not None:
                raw_identifier = (payload.identifier or "").strip()
                requested_type = (payload.wallet_type or "").strip().lower() or None
                if requested_type and requested_type != "auto":
                    chain = normalize_wallet_chain(requested_type)
                    if chain not in {"ethereum", "bitcoin", "solana"}:
                        raise HTTPException(status_code=400, detail="wallet_type must be auto, ethereum, bitcoin or solana")
                    identifier = raw_identifier
                    if chain == "bitcoin" and not is_bitcoin_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid bitcoin wallet address")
                    if chain == "solana" and not is_solana_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid solana wallet address")
                else:
                    chain, identifier = parse_wallet_identifier(raw_identifier)
                if not identifier:
                    raise HTTPException(status_code=400, detail="identifier cannot be empty")
                next_identifier = encode_wallet_identifier(identifier, chain)
            elif payload.wallet_type is not None:
                chain, identifier = parse_wallet_identifier(a.identifier)
                requested_type = (payload.wallet_type or "").strip().lower()
                if requested_type and requested_type != "auto":
                    chain = normalize_wallet_chain(requested_type)
                    if chain not in {"ethereum", "bitcoin", "solana"}:
                        raise HTTPException(status_code=400, detail="wallet_type must be auto, ethereum, bitcoin or solana")
                    if chain == "bitcoin" and not is_bitcoin_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid bitcoin wallet address")
                    if chain == "solana" and not is_solana_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid solana wallet address")
                    next_identifier = encode_wallet_identifier(identifier, chain)

            a.identifier = next_identifier

            if payload.label is not None:
                label = payload.label.strip()
                a.label = label or None

            s.add(a)
            s.commit()
            s.refresh(a)
            chain, wallet_identifier = parse_wallet_identifier(a.identifier)
            return {
                "id": a.id,
                "identifier": wallet_identifier,
                "label": a.label,
                "wallet_type": chain,
            }
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to update wallet id=%s", wallet_id)
        raise HTTPException(status_code=500, detail="failed to update wallet")
