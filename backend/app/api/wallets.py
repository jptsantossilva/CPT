import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import get_session
from ..models import Account
from ..wallet_chains import (
    encode_wallet_identifier,
    is_bitcoin_mainnet_identifier,
    is_bitcoin_testnet_identifier,
    is_solana_address,
    normalize_wallet_chain,
    parse_wallet_identifier,
)

router = APIRouter(prefix="/admin/wallets", tags=["admin"])
log = logging.getLogger(__name__)
_TESTNET_NOT_SUPPORTED = "Testnet not supported"


class CreateWallet(BaseModel):
    identifier: str  # wallet address
    wallet_type: str | None = None  # auto|ethereum|bitcoin|solana
    label: str | None = None


class UpdateWallet(BaseModel):
    identifier: str | None = None
    wallet_type: str | None = None  # auto|ethereum|bitcoin|solana
    label: str | None = None


def _assert_valid_bitcoin_identifier(identifier: str) -> None:
    if is_bitcoin_testnet_identifier(identifier):
        raise HTTPException(status_code=400, detail=_TESTNET_NOT_SUPPORTED)
    if not is_bitcoin_mainnet_identifier(identifier):
        raise HTTPException(status_code=400, detail="invalid bitcoin wallet identifier")


def _canonicalize_wallet_identifier(chain: str, identifier: str) -> str:
    wallet = (identifier or "").strip()
    if chain == "ethereum":
        return wallet.lower()
    if chain == "bitcoin" and wallet.lower().startswith("bc1"):
        return wallet.lower()
    return wallet


def _normalize_encoded_wallet_identifier(identifier: str) -> str:
    chain, wallet_identifier = parse_wallet_identifier(identifier)
    canonical_identifier = _canonicalize_wallet_identifier(chain, wallet_identifier)
    return encode_wallet_identifier(canonical_identifier, chain)


def _ensure_wallet_not_duplicate(
    session,
    *,
    encoded_identifier: str,
    exclude_wallet_id: int | None = None,
) -> None:
    rows = session.query(Account).filter(Account.provider == "wallet").all()
    normalized_target = _normalize_encoded_wallet_identifier(encoded_identifier)
    for row in rows:
        if exclude_wallet_id is not None and int(row.id or 0) == int(exclude_wallet_id):
            continue
        normalized_existing = _normalize_encoded_wallet_identifier(row.identifier or "")
        if normalized_existing == normalized_target:
            raise HTTPException(status_code=400, detail="wallet already exists")


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
            if chain == "bitcoin":
                _assert_valid_bitcoin_identifier(wallet_identifier)
            if chain == "solana" and not is_solana_address(wallet_identifier):
                raise HTTPException(status_code=400, detail="invalid solana wallet address")
        else:
            if is_bitcoin_testnet_identifier(raw_identifier):
                raise HTTPException(status_code=400, detail=_TESTNET_NOT_SUPPORTED)
            chain, wallet_identifier = parse_wallet_identifier(raw_identifier)
            if chain == "bitcoin":
                _assert_valid_bitcoin_identifier(wallet_identifier)
        if not wallet_identifier:
            raise HTTPException(status_code=400, detail="identifier cannot be empty")
        wallet_identifier = _canonicalize_wallet_identifier(chain, wallet_identifier)
        encoded_identifier = encode_wallet_identifier(wallet_identifier, chain)
        with get_session() as s:
            _ensure_wallet_not_duplicate(s, encoded_identifier=encoded_identifier)
            a = Account(
                provider="wallet",
                identifier=encoded_identifier,
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
                    if chain == "bitcoin":
                        _assert_valid_bitcoin_identifier(identifier)
                    if chain == "solana" and not is_solana_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid solana wallet address")
                else:
                    if is_bitcoin_testnet_identifier(raw_identifier):
                        raise HTTPException(status_code=400, detail=_TESTNET_NOT_SUPPORTED)
                    chain, identifier = parse_wallet_identifier(raw_identifier)
                    if chain == "bitcoin":
                        _assert_valid_bitcoin_identifier(identifier)
                if not identifier:
                    raise HTTPException(status_code=400, detail="identifier cannot be empty")
                identifier = _canonicalize_wallet_identifier(chain, identifier)
                next_identifier = encode_wallet_identifier(identifier, chain)
            elif payload.wallet_type is not None:
                chain, identifier = parse_wallet_identifier(a.identifier)
                requested_type = (payload.wallet_type or "").strip().lower()
                if requested_type and requested_type != "auto":
                    chain = normalize_wallet_chain(requested_type)
                    if chain not in {"ethereum", "bitcoin", "solana"}:
                        raise HTTPException(status_code=400, detail="wallet_type must be auto, ethereum, bitcoin or solana")
                    if chain == "bitcoin":
                        _assert_valid_bitcoin_identifier(identifier)
                    if chain == "solana" and not is_solana_address(identifier):
                        raise HTTPException(status_code=400, detail="invalid solana wallet address")
                    identifier = _canonicalize_wallet_identifier(chain, identifier)
                    next_identifier = encode_wallet_identifier(identifier, chain)

            _ensure_wallet_not_duplicate(s, encoded_identifier=next_identifier, exclude_wallet_id=wallet_id)

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
