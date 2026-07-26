from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api import fiat_cashflows
from backend.app import main
from backend.app.models import FiatCashFlow, Snapshot
from backend.app.services import fiat


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _payload(**overrides):
    values = {
        "flow_type": "deposit",
        "occurred_on": date(2026, 1, 10),
        "original_currency": "EUR",
        "original_amount": "1000.00",
        "counter_amount": "1100.00",
        "counterparty_type": "bank",
        "counterparty_name": "Example Bank",
        "notes": "Initial contribution",
    }
    values.update(overrides)
    return fiat_cashflows.FiatCashFlowPayload(**values)


def _flow(
    *,
    flow_type: str,
    occurred_on: date,
    eur: str,
    usd: str,
    name: str = "Example Bank",
) -> FiatCashFlow:
    return FiatCashFlow(
        flow_type=flow_type,
        occurred_on=occurred_on,
        original_currency="EUR",
        original_amount=Decimal(eur),
        amount_eur=Decimal(eur),
        amount_usd=Decimal(usd),
        counterparty_type="bank",
        counterparty_name=name,
    )


def test_payload_validation_and_currency_normalization():
    eur_payload = _payload()
    assert fiat_cashflows._normalized_amounts(eur_payload) == (
        Decimal("1000.00"),
        Decimal("1100.00"),
    )

    usd_payload = _payload(
        original_currency="USD",
        original_amount="550.00",
        counter_amount="500.00",
    )
    assert fiat_cashflows._normalized_amounts(usd_payload) == (
        Decimal("500.00"),
        Decimal("550.00"),
    )

    with pytest.raises(ValidationError):
        _payload(original_amount="0")
    with pytest.raises(ValidationError):
        _payload(counterparty_name="  ")
    with pytest.raises(ValidationError):
        _payload(occurred_on=datetime.utcnow().date() + timedelta(days=1))


def test_cashflow_crud(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(fiat_cashflows, "get_session", lambda: Session(engine))

    created = fiat_cashflows.create_cashflow(_payload())
    assert created["id"] is not None
    assert created["amount_eur"] == "1000.00"
    assert created["amount_usd"] == "1100.00"

    rows = fiat_cashflows.list_cashflows()
    assert len(rows) == 1
    assert rows[0]["counterparty_name"] == "Example Bank"

    updated = fiat_cashflows.update_cashflow(
        int(created["id"]),
        _payload(
            flow_type="withdrawal",
            original_currency="USD",
            original_amount="220.00",
            counter_amount="200.00",
            counterparty_type="person",
            counterparty_name="Maria",
            notes=None,
        ),
    )
    assert updated["flow_type"] == "withdrawal"
    assert updated["amount_eur"] == "200.00"
    assert updated["amount_usd"] == "220.00"
    assert updated["counterparty_name"] == "Maria"

    assert fiat_cashflows.delete_cashflow(int(created["id"])) == {"deleted": created["id"]}
    assert fiat_cashflows.list_cashflows() == []


def test_performance_uses_full_snapshot_total_and_excludes_pending_flows():
    snapshot = Snapshot(
        id=7,
        timestamp=datetime(2026, 2, 15, 12, 0),
        total_eur=900,
        total_usd=990,
        meta=(
            '{"totals":{"coins_eur":900,"coins_usd":990,'
            '"nfts_eur":100,"nfts_usd":110,'
            '"portfolio_eur":1000,"portfolio_usd":1100}}'
        ),
    )
    rows = [
        _flow(
            flow_type="deposit",
            occurred_on=date(2026, 1, 1),
            eur="800.00",
            usd="880.00",
        ),
        _flow(
            flow_type="withdrawal",
            occurred_on=date(2026, 2, 1),
            eur="100.00",
            usd="110.00",
            name="Maria",
        ),
        _flow(
            flow_type="deposit",
            occurred_on=date(2026, 2, 16),
            eur="50.00",
            usd="55.00",
        ),
    ]

    result = fiat.build_performance(snapshot, rows)

    assert result["snapshot"]["id"] == 7
    assert result["eur"] == {
        "deposits": "800.00",
        "withdrawals": "100.00",
        "net_invested": "700.00",
        "current_portfolio": "1000.00",
        "pnl": "300.00",
        "pnl_pct": "42.86",
        "status": "gain",
    }
    assert result["usd"]["pnl"] == "330.00"
    assert result["pending"]["count"] == 1
    assert result["pending"]["eur"]["deposits"] == "50.00"
    assert len(result["by_counterparty"]) == 2


def test_performance_loss_breakeven_and_no_snapshot():
    deposit = _flow(
        flow_type="deposit",
        occurred_on=date(2026, 1, 1),
        eur="1000.00",
        usd="1100.00",
    )

    loss = fiat.build_performance(
        Snapshot(timestamp=datetime(2026, 1, 2), total_eur=900, total_usd=990),
        [deposit],
    )
    assert loss["eur"]["pnl"] == "-100.00"
    assert loss["eur"]["pnl_pct"] == "-10.00"
    assert loss["eur"]["status"] == "loss"

    breakeven = fiat.build_performance(
        Snapshot(timestamp=datetime(2026, 1, 2), total_eur=1000, total_usd=1100),
        [deposit],
    )
    assert breakeven["eur"]["status"] == "breakeven"

    unavailable = fiat.build_performance(None, [deposit])
    assert unavailable["snapshot"] is None
    assert unavailable["eur"]["current_portfolio"] is None
    assert unavailable["eur"]["pnl"] is None
    assert unavailable["eur"]["status"] == "unavailable"
    assert unavailable["pending"]["count"] == 1

    no_baseline = fiat.build_performance(
        Snapshot(timestamp=datetime(2026, 1, 2), total_eur=1000, total_usd=1100),
        [],
    )
    assert no_baseline["eur"]["pnl"] is None
    assert no_baseline["eur"]["pnl_pct"] is None
    assert no_baseline["eur"]["status"] == "unavailable"


def test_performance_supports_withdrawals_above_initial_contributions():
    rows = [
        _flow(
            flow_type="deposit",
            occurred_on=date(2026, 1, 1),
            eur="1000.00",
            usd="1100.00",
        ),
        _flow(
            flow_type="withdrawal",
            occurred_on=date(2026, 1, 2),
            eur="1200.00",
            usd="1320.00",
        ),
    ]
    result = fiat.build_performance(
        Snapshot(timestamp=datetime(2026, 1, 3), total_eur=50, total_usd=55),
        rows,
    )
    assert result["eur"]["net_invested"] == "-200.00"
    assert result["eur"]["pnl"] == "250.00"
    assert result["eur"]["pnl_pct"] is None
    assert result["eur"]["status"] == "gain"


def test_performance_endpoint_ignores_latest_invalid_snapshot(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Snapshot(
                timestamp=datetime(2026, 1, 2),
                total_eur=1000,
                total_usd=1100,
                is_valid=True,
            )
        )
        session.add(
            Snapshot(
                timestamp=datetime(2026, 1, 3),
                total_eur=9999,
                total_usd=9999,
                is_valid=False,
            )
        )
        session.add(
            _flow(
                flow_type="deposit",
                occurred_on=date(2026, 1, 1),
                eur="800.00",
                usd="880.00",
            )
        )
        session.commit()

    monkeypatch.setattr(main.db, "get_session", lambda: Session(engine))
    result = main.portfolio_performance()
    assert result["eur"]["current_portfolio"] == "1000.00"
    assert result["eur"]["pnl"] == "200.00"
