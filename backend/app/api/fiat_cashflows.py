import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, condecimal, validator
from sqlmodel import select

from ..db import get_session
from ..models import FiatCashFlow
from ..services.fiat import money, money_string


router = APIRouter(prefix="/admin/fiat-cashflows", tags=["admin"])
log = logging.getLogger(__name__)
Amount = condecimal(gt=0, max_digits=20, decimal_places=2)


class FiatCashFlowPayload(BaseModel):
    flow_type: Literal["deposit", "withdrawal"]
    occurred_on: date
    original_currency: Literal["EUR", "USD"]
    original_amount: Amount
    counter_amount: Amount
    counterparty_type: Literal["bank", "person"]
    counterparty_name: str
    notes: str | None = None

    @validator("occurred_on")
    def validate_date(cls, value: date) -> date:
        if value > datetime.utcnow().date():
            raise ValueError("occurred_on cannot be in the future")
        return value

    @validator("counterparty_name")
    def validate_counterparty_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("counterparty_name cannot be empty")
        if len(cleaned) > 200:
            raise ValueError("counterparty_name cannot exceed 200 characters")
        return cleaned

    @validator("notes")
    def validate_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 1000:
            raise ValueError("notes cannot exceed 1000 characters")
        return cleaned or None


def _normalized_amounts(payload: FiatCashFlowPayload) -> tuple[Decimal, Decimal]:
    original = money(payload.original_amount)
    counter = money(payload.counter_amount)
    return (original, counter) if payload.original_currency == "EUR" else (counter, original)


def serialize_cashflow(row: FiatCashFlow) -> dict:
    counter_amount = row.amount_usd if row.original_currency == "EUR" else row.amount_eur
    return {
        "id": row.id,
        "flow_type": row.flow_type,
        "occurred_on": row.occurred_on,
        "original_currency": row.original_currency,
        "original_amount": money_string(row.original_amount),
        "counter_amount": money_string(counter_amount),
        "amount_eur": money_string(row.amount_eur),
        "amount_usd": money_string(row.amount_usd),
        "counterparty_type": row.counterparty_type,
        "counterparty_name": row.counterparty_name,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _apply_payload(row: FiatCashFlow, payload: FiatCashFlowPayload) -> None:
    amount_eur, amount_usd = _normalized_amounts(payload)
    row.flow_type = payload.flow_type
    row.occurred_on = payload.occurred_on
    row.original_currency = payload.original_currency
    row.original_amount = money(payload.original_amount)
    row.amount_eur = amount_eur
    row.amount_usd = amount_usd
    row.counterparty_type = payload.counterparty_type
    row.counterparty_name = payload.counterparty_name
    row.notes = payload.notes
    row.updated_at = datetime.utcnow()


@router.get("/")
def list_cashflows():
    with get_session() as session:
        rows = session.exec(
            select(FiatCashFlow)
            .order_by(FiatCashFlow.occurred_on.desc(), FiatCashFlow.id.desc())
        ).all()
        return [serialize_cashflow(row) for row in rows]


@router.post("/")
def create_cashflow(payload: FiatCashFlowPayload):
    try:
        row = FiatCashFlow(
            flow_type=payload.flow_type,
            occurred_on=payload.occurred_on,
            original_currency=payload.original_currency,
            original_amount=money(payload.original_amount),
            amount_eur=Decimal("0"),
            amount_usd=Decimal("0"),
            counterparty_type=payload.counterparty_type,
            counterparty_name=payload.counterparty_name,
            notes=payload.notes,
        )
        _apply_payload(row, payload)
        with get_session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return serialize_cashflow(row)
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to create fiat cash flow")
        raise HTTPException(status_code=500, detail="failed to create fiat cash flow")


@router.put("/{cashflow_id}")
def update_cashflow(cashflow_id: int, payload: FiatCashFlowPayload):
    try:
        with get_session() as session:
            row = session.get(FiatCashFlow, cashflow_id)
            if row is None:
                raise HTTPException(status_code=404, detail="fiat cash flow not found")
            _apply_payload(row, payload)
            session.add(row)
            session.commit()
            session.refresh(row)
            return serialize_cashflow(row)
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to update fiat cash flow id=%s", cashflow_id)
        raise HTTPException(status_code=500, detail="failed to update fiat cash flow")


@router.delete("/{cashflow_id}")
def delete_cashflow(cashflow_id: int):
    try:
        with get_session() as session:
            row = session.get(FiatCashFlow, cashflow_id)
            if row is None:
                raise HTTPException(status_code=404, detail="fiat cash flow not found")
            session.delete(row)
            session.commit()
            return {"deleted": cashflow_id}
    except HTTPException:
        raise
    except Exception:
        log.exception("failed to delete fiat cash flow id=%s", cashflow_id)
        raise HTTPException(status_code=500, detail="failed to delete fiat cash flow")
