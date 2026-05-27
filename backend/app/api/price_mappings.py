from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..db import get_session
from ..models import PriceSymbolMapping
from ..services import prices

router = APIRouter(prefix="/admin/price-mappings", tags=["admin"])


class PriceMappingPayload(BaseModel):
    symbol: str
    provider_id: str
    label: str | None = None
    enabled: bool = True
    notes: str | None = None


def _normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if not value:
        raise HTTPException(status_code=400, detail="symbol is required")
    return value


def _normalize_provider_id(provider_id: str) -> str:
    value = str(provider_id or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="provider_id is required")
    return value


def _serialize(row: PriceSymbolMapping) -> dict:
    return {
        "symbol": row.symbol,
        "provider": row.provider,
        "provider_id": row.provider_id,
        "label": row.label,
        "enabled": bool(row.enabled),
        "notes": row.notes,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/")
def list_price_mappings():
    with get_session() as s:
        rows = s.exec(select(PriceSymbolMapping).order_by(PriceSymbolMapping.symbol.asc())).all()
        return [_serialize(row) for row in rows]


@router.post("/")
def create_price_mapping(payload: PriceMappingPayload):
    symbol = _normalize_symbol(payload.symbol)
    provider_id = _normalize_provider_id(payload.provider_id)
    with get_session() as s:
        if s.get(PriceSymbolMapping, symbol):
            raise HTTPException(status_code=400, detail="price mapping already exists")
        row = PriceSymbolMapping(
            symbol=symbol,
            provider="coingecko",
            provider_id=provider_id,
            label=(payload.label or "").strip() or None,
            enabled=bool(payload.enabled),
            notes=(payload.notes or "").strip() or None,
            updated_at=datetime.utcnow(),
        )
        s.add(row)
        s.commit()
        s.refresh(row)
    prices.clear_symbol_mapping_cache(symbol)
    return _serialize(row)


@router.put("/{symbol}")
def update_price_mapping(symbol: str, payload: PriceMappingPayload):
    current_symbol = _normalize_symbol(symbol)
    next_symbol = _normalize_symbol(payload.symbol)
    provider_id = _normalize_provider_id(payload.provider_id)
    with get_session() as s:
        row = s.get(PriceSymbolMapping, current_symbol)
        if not row:
            raise HTTPException(status_code=404, detail="price mapping not found")
        if next_symbol != current_symbol and s.get(PriceSymbolMapping, next_symbol):
            raise HTTPException(status_code=400, detail="price mapping already exists")
        if next_symbol != current_symbol:
            s.delete(row)
            row = PriceSymbolMapping(symbol=next_symbol, provider="coingecko", provider_id=provider_id)
        row.provider_id = provider_id
        row.label = (payload.label or "").strip() or None
        row.enabled = bool(payload.enabled)
        row.notes = (payload.notes or "").strip() or None
        row.updated_at = datetime.utcnow()
        s.add(row)
        s.commit()
        s.refresh(row)
    prices.clear_symbol_mapping_cache(current_symbol)
    if next_symbol != current_symbol:
        prices.clear_symbol_mapping_cache(next_symbol)
    return _serialize(row)


@router.delete("/{symbol}")
def delete_price_mapping(symbol: str):
    key = _normalize_symbol(symbol)
    with get_session() as s:
        row = s.get(PriceSymbolMapping, key)
        if not row:
            raise HTTPException(status_code=404, detail="price mapping not found")
        s.delete(row)
        s.commit()
    prices.clear_symbol_mapping_cache(key)
    return {"status": "deleted"}
