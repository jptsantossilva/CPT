"""Administration API for read-only exchange credentials."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..crypto import decrypt_text, encrypt_text
from ..db import get_session
from ..models import Account

router = APIRouter(prefix="/admin/exchange-accounts", tags=["admin"])
log = logging.getLogger(__name__)

PROVIDERS = {"binance", "okx", "kraken"}
OKX_REGIONS = {"eea", "global", "us"}


class CreateExchangeAccount(BaseModel):
    provider: str
    identifier: str
    label: str | None = None
    api_key: str
    api_secret: str
    api_passphrase: str | None = None
    region: str | None = None
    include_subaccounts: bool | None = None


class UpdateExchangeAccount(BaseModel):
    provider: str | None = None
    identifier: str | None = None
    label: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None
    region: str | None = None
    include_subaccounts: bool | None = None


def _masked_key(account: Account) -> str:
    if not account.api_key_encrypted:
        return "********"
    try:
        value = decrypt_text(account.api_key_encrypted).strip()
        return f"{value[:4]}****{value[-4:]}" if len(value) > 8 else "********"
    except Exception:
        return "********"


def _serialize(account: Account, *, legacy_binance_count: int | None = None) -> dict:
    provider = str(account.provider or "").lower()
    include = account.include_subaccounts
    if include is None:
        include = (
            legacy_binance_count == 1
            if provider == "binance" and legacy_binance_count is not None
            else provider in {"binance", "okx"}
        )
    return {
        "id": account.id,
        "provider": provider,
        "identifier": account.identifier,
        "label": account.label,
        "api_key_masked": _masked_key(account),
        "api_secret_masked": "********",
        "api_passphrase_masked": "********" if account.api_passphrase_encrypted else None,
        "region": account.provider_region if provider == "okx" else None,
        "include_subaccounts": bool(include) if provider != "kraken" else False,
    }


def _validated(
    provider: str,
    identifier: str,
    api_key: str,
    api_secret: str,
    passphrase: str | None,
    region: str | None,
) -> tuple[str, str, str, str, str | None, str | None]:
    provider = provider.strip().lower()
    identifier = identifier.strip()
    api_key = api_key.strip()
    api_secret = api_secret.strip()
    passphrase = (passphrase or "").strip() or None
    region = (region or "").strip().lower() or None
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="provider must be binance, okx, or kraken")
    if not identifier or not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="identifier, API key, and API secret are required")
    if provider == "okx":
        if not passphrase:
            raise HTTPException(status_code=400, detail="OKX passphrase is required")
        region = region or "eea"
        if region not in OKX_REGIONS:
            raise HTTPException(status_code=400, detail="OKX region must be EEA, Global, or US")
    elif passphrase or region:
        raise HTTPException(status_code=400, detail="passphrase and region are only valid for OKX")
    return provider, identifier, api_key, api_secret, passphrase, region


@router.get("/")
def list_accounts():
    with get_session() as session:
        rows = (
            session.query(Account)
            .filter(Account.is_exchange == True, Account.provider.in_(PROVIDERS))  # noqa: E712
            .order_by(Account.provider, Account.id)
            .all()
        )
        binance_count = sum(1 for row in rows if row.provider == "binance")
        return [
            _serialize(row, legacy_binance_count=binance_count)
            for row in rows
        ]


@router.post("/")
def create_account(payload: CreateExchangeAccount):
    provider, identifier, api_key, api_secret, passphrase, region = _validated(
        payload.provider,
        payload.identifier,
        payload.api_key,
        payload.api_secret,
        payload.api_passphrase,
        payload.region,
    )
    try:
        with get_session() as session:
            duplicate = (
                session.query(Account)
                .filter(Account.provider == provider, Account.identifier == identifier)
                .first()
            )
            if duplicate:
                raise HTTPException(status_code=409, detail="exchange account already exists")
            account = Account(
                provider=provider,
                identifier=identifier,
                label=(payload.label or "").strip() or None,
                api_key_encrypted=encrypt_text(api_key),
                api_secret_encrypted=encrypt_text(api_secret),
                api_passphrase_encrypted=encrypt_text(passphrase) if passphrase else None,
                provider_region=region,
                include_subaccounts=(
                    False if provider == "kraken"
                    else payload.include_subaccounts if payload.include_subaccounts is not None
                    else True
                ),
                is_exchange=True,
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            return _serialize(account)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("failed to create exchange account provider=%s", provider)
        raise HTTPException(status_code=500, detail="failed to create exchange account")


@router.put("/{account_id}")
def update_account(account_id: int, payload: UpdateExchangeAccount):
    try:
        with get_session() as session:
            account = session.get(Account, account_id)
            if not account or account.provider not in PROVIDERS or not account.is_exchange:
                raise HTTPException(status_code=404, detail="not found")
            if payload.provider is not None and payload.provider.strip().lower() != account.provider:
                raise HTTPException(status_code=400, detail="provider cannot be changed")
            if payload.identifier is not None:
                identifier = payload.identifier.strip()
                if not identifier:
                    raise HTTPException(status_code=400, detail="identifier cannot be empty")
                duplicate = (
                    session.query(Account)
                    .filter(
                        Account.provider == account.provider,
                        Account.identifier == identifier,
                        Account.id != account.id,
                    )
                    .first()
                )
                if duplicate:
                    raise HTTPException(status_code=409, detail="exchange account already exists")
                account.identifier = identifier
            fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))
            if "label" in fields_set:
                account.label = (payload.label or "").strip() or None
            if payload.api_key is not None and payload.api_key.strip():
                account.api_key_encrypted = encrypt_text(payload.api_key.strip())
            if payload.api_secret is not None and payload.api_secret.strip():
                account.api_secret_encrypted = encrypt_text(payload.api_secret.strip())
            if account.provider == "okx":
                if payload.api_passphrase is not None and payload.api_passphrase.strip():
                    account.api_passphrase_encrypted = encrypt_text(payload.api_passphrase.strip())
                if payload.region is not None:
                    region = payload.region.strip().lower()
                    if region not in OKX_REGIONS:
                        raise HTTPException(status_code=400, detail="OKX region must be EEA, Global, or US")
                    account.provider_region = region
            elif payload.api_passphrase or payload.region:
                raise HTTPException(status_code=400, detail="passphrase and region are only valid for OKX")
            if payload.include_subaccounts is not None:
                account.include_subaccounts = (
                    False if account.provider == "kraken" else payload.include_subaccounts
                )
            session.add(account)
            session.commit()
            session.refresh(account)
            return _serialize(account)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("failed to update exchange account id=%s", account_id)
        raise HTTPException(status_code=500, detail="failed to update exchange account")


@router.delete("/{account_id}")
def delete_account(account_id: int):
    with get_session() as session:
        account = session.get(Account, account_id)
        if not account or account.provider not in PROVIDERS or not account.is_exchange:
            raise HTTPException(status_code=404, detail="not found")
        session.delete(account)
        session.commit()
        return {"deleted": account_id}
