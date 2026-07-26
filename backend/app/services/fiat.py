import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable


_CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Convert a stored/API amount to an exact two-decimal monetary value."""
    try:
        return Decimal(str(value or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def money_string(value: Any) -> str:
    return format(money(value), ".2f")


def snapshot_portfolio_totals(snapshot: Any) -> tuple[Decimal, Decimal]:
    """Return full coin + NFT totals, with legacy snapshot fallbacks."""
    fallback_eur = money(getattr(snapshot, "total_eur", 0))
    fallback_usd = money(getattr(snapshot, "total_usd", 0))
    raw_meta = getattr(snapshot, "meta", None)
    if not raw_meta:
        return fallback_eur, fallback_usd
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except Exception:
        return fallback_eur, fallback_usd
    if not isinstance(meta, dict):
        return fallback_eur, fallback_usd
    totals = meta.get("totals")
    if not isinstance(totals, dict):
        return fallback_eur, fallback_usd
    return (
        money(totals.get("portfolio_eur", fallback_eur)),
        money(totals.get("portfolio_usd", fallback_usd)),
    )


def _empty_sums() -> dict[str, Decimal]:
    return {
        "deposits_eur": Decimal("0.00"),
        "deposits_usd": Decimal("0.00"),
        "withdrawals_eur": Decimal("0.00"),
        "withdrawals_usd": Decimal("0.00"),
    }


def _add_flow(sums: dict[str, Decimal], flow: Any) -> None:
    prefix = "deposits" if flow.flow_type == "deposit" else "withdrawals"
    sums[f"{prefix}_eur"] += money(flow.amount_eur)
    sums[f"{prefix}_usd"] += money(flow.amount_usd)


def _currency_summary(
    sums: dict[str, Decimal],
    currency: str,
    current: Decimal | None,
) -> dict[str, str | None]:
    key = currency.lower()
    deposits = sums[f"deposits_{key}"]
    withdrawals = sums[f"withdrawals_{key}"]
    net_invested = deposits - withdrawals
    # A portfolio without any recorded contribution has no meaningful cost
    # baseline, even when a current snapshot exists.
    pnl = (
        current + withdrawals - deposits
        if current is not None and deposits > 0
        else None
    )
    if pnl is None:
        status = "unavailable"
    elif pnl > 0:
        status = "gain"
    elif pnl < 0:
        status = "loss"
    else:
        status = "breakeven"
    return {
        "deposits": money_string(deposits),
        "withdrawals": money_string(withdrawals),
        "net_invested": money_string(net_invested),
        "current_portfolio": money_string(current) if current is not None else None,
        "pnl": money_string(pnl) if pnl is not None else None,
        "status": status,
    }


def build_performance(snapshot: Any | None, cashflows: Iterable[Any]) -> dict[str, Any]:
    rows = list(cashflows)
    snapshot_date: date | None = None
    current_eur: Decimal | None = None
    current_usd: Decimal | None = None
    if snapshot is not None:
        timestamp = getattr(snapshot, "timestamp", None)
        snapshot_date = timestamp.date() if timestamp is not None else None
        current_eur, current_usd = snapshot_portfolio_totals(snapshot)

    included_sums = _empty_sums()
    pending_sums = _empty_sums()
    pending_count = 0
    counterparties: dict[tuple[str, str], dict[str, Any]] = {}

    for flow in rows:
        is_pending = snapshot_date is None or flow.occurred_on > snapshot_date
        if is_pending:
            pending_count += 1
            _add_flow(pending_sums, flow)
        else:
            _add_flow(included_sums, flow)

        group_key = (flow.counterparty_type, flow.counterparty_name)
        group = counterparties.setdefault(
            group_key,
            {
                "counterparty_type": flow.counterparty_type,
                "counterparty_name": flow.counterparty_name,
                **_empty_sums(),
            },
        )
        _add_flow(group, flow)

    by_counterparty = []
    for group in sorted(
        counterparties.values(),
        key=lambda item: (item["counterparty_type"], item["counterparty_name"].lower()),
    ):
        by_counterparty.append(
            {
                "counterparty_type": group["counterparty_type"],
                "counterparty_name": group["counterparty_name"],
                "eur": _currency_summary(group, "EUR", None),
                "usd": _currency_summary(group, "USD", None),
            }
        )

    return {
        "snapshot": (
            {
                "id": getattr(snapshot, "id", None),
                "timestamp": getattr(snapshot, "timestamp", None),
            }
            if snapshot is not None
            else None
        ),
        "eur": _currency_summary(included_sums, "EUR", current_eur),
        "usd": _currency_summary(included_sums, "USD", current_usd),
        "pending": {
            "count": pending_count,
            "eur": _currency_summary(pending_sums, "EUR", None),
            "usd": _currency_summary(pending_sums, "USD", None),
        },
        "by_counterparty": by_counterparty,
    }
