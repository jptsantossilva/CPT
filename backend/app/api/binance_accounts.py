import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import get_session
from ..models import Account
from ..crypto import decrypt_text, encrypt_text

router = APIRouter(prefix="/admin/binance-accounts", tags=["admin"])
log = logging.getLogger(__name__)


class CreateAccount(BaseModel):
    identifier: str
    label: str | None = None
    api_key: str
    api_secret: str


class UpdateAccount(BaseModel):
    identifier: str | None = None
    label: str | None = None
    api_key: str | None = None
    api_secret: str | None = None


def _mask_secret(value: str, visible_start: int = 4, visible_end: int = 4) -> str:
    raw = value.strip()
    if not raw:
        return "********"
    if len(raw) <= visible_start + visible_end:
        if len(raw) <= 2:
            return "*" * len(raw)
        return f"{raw[:1]}{'*' * max(len(raw) - 2, 1)}{raw[-1:]}"
    return f"{raw[:visible_start]}****{raw[-visible_end:]}"


def _masked_key_for_account(account: Account) -> str:
    if not account.api_key_encrypted:
        return "********"
    try:
        return _mask_secret(decrypt_text(account.api_key_encrypted))
    except Exception:
        return "********"


@router.post("/")
def create_account(payload: CreateAccount):
    try:
        encrypted_key = encrypt_text(payload.api_key)
        encrypted_secret = encrypt_text(payload.api_secret)
    except RuntimeError as exc:
        log.warning("failed to encrypt Binance credentials: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        with get_session() as s:
            a = Account(
                provider="binance",
                identifier=payload.identifier,
                label=payload.label,
                api_key_encrypted=encrypted_key,
                api_secret_encrypted=encrypted_secret,
                is_exchange=True,
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            return {"id": a.id, "identifier": a.identifier, "label": a.label}
    except Exception:
        log.exception("failed to create Binance account")
        raise HTTPException(status_code=500, detail="failed to create Binance account")


@router.get("/")
def list_accounts():
    try:
        with get_session() as s:
            rows = s.query(Account).filter(Account.provider == "binance").all()
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r.id,
                        "identifier": r.identifier,
                        "label": r.label,
                        "api_key_masked": _masked_key_for_account(r),
                        "api_secret_masked": "********",
                    }
                )
            return out
    except Exception:
        log.exception("failed to list Binance accounts")
        raise HTTPException(status_code=500, detail="failed to list Binance accounts")


@router.put("/{account_id}")
def update_account(account_id: int, payload: UpdateAccount):
    try:
        with get_session() as s:
            a = s.get(Account, account_id)
            if not a or a.provider != "binance":
                raise HTTPException(status_code=404, detail="not found")

            if payload.identifier is not None:
                identifier = payload.identifier.strip()
                if not identifier:
                    raise HTTPException(status_code=400, detail="identifier cannot be empty")
                a.identifier = identifier

            if payload.label is not None:
                label = payload.label.strip()
                a.label = label or None

            if payload.api_key is not None:
                api_key = payload.api_key.strip()
                if api_key:
                    a.api_key_encrypted = encrypt_text(api_key)

            if payload.api_secret is not None:
                api_secret = payload.api_secret.strip()
                if api_secret:
                    a.api_secret_encrypted = encrypt_text(api_secret)

            s.add(a)
            s.commit()
            s.refresh(a)
            return {
                "id": a.id,
                "identifier": a.identifier,
                "label": a.label,
                "api_key_masked": _masked_key_for_account(a),
                "api_secret_masked": "********",
            }
    except HTTPException:
        raise
    except RuntimeError as exc:
        log.warning("failed to encrypt Binance credentials on update id=%s: %s", account_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception("failed to update Binance account id=%s", account_id)
        raise HTTPException(status_code=500, detail="failed to update Binance account")


@router.delete("/{account_id}")
def delete_account(account_id: int):
    try:
        with get_session() as s:
            a = s.get(Account, account_id)
            if not a:
                raise HTTPException(status_code=404, detail="not found")
            s.delete(a)
            s.commit()
            return {"deleted": account_id}
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to delete Binance account id=%s", account_id)
        raise HTTPException(status_code=500, detail="failed to delete Binance account")
