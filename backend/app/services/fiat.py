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
    *,
    require_deposit: bool = True,
) -> dict[str, str | None]:
    key = currency.lower()
    deposits = sums[f"deposits_{key}"]
    withdrawals = sums[f"withdrawals_{key}"]
    net_invested = deposits - withdrawals
    # A portfolio without any recorded contribution has no meaningful cost
    # baseline, even when a current snapshot exists.
    pnl = (
        current + withdrawals - deposits
        if current is not None and (deposits > 0 or not require_deposit)
        else None
    )
    # This is the return relative to capital that remains invested. It is not
    # meaningful once withdrawals exceed contributions, so leave it unavailable.
    pnl_pct = (pnl / net_invested * 100) if pnl is not None and net_invested > 0 else None
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
        "pnl_pct": money_string(pnl_pct) if pnl_pct is not None else None,
        "status": status,
    }


def _person_key(name: Any) -> str:
    return str(name or "").strip().casefold()


def _new_allocation_group(counterparty_type: str, counterparty_name: str) -> dict[str, Any]:
    return {
        "counterparty_type": counterparty_type,
        "counterparty_name": counterparty_name,
        "included": _empty_sums(),
        "pending": _empty_sums(),
        "pending_count": 0,
        "last_order": None,
        "allocation_pct": None,
        "current_eur": None,
        "current_usd": None,
    }


def _positive_net_eur(group: dict[str, Any]) -> Decimal:
    sums = group["included"]
    return max(sums["deposits_eur"] - sums["withdrawals_eur"], Decimal("0.00"))


def _allocate_current(
    groups: dict[tuple[str, str], dict[str, Any]],
    current_eur: Decimal | None,
    current_usd: Decimal | None,
) -> None:
    """Allocate the snapshot using stable EUR capital weights.

    Rounded allocations are reconciled back to the snapshot total by assigning
    the cent residual to the group with the largest positive capital balance.
    """
    if current_eur is None or current_usd is None:
        return

    eligible = [group for group in groups.values() if _positive_net_eur(group) > 0]
    total_weight = sum((_positive_net_eur(group) for group in eligible), Decimal("0.00"))
    if total_weight <= 0:
        for group in groups.values():
            group["current_eur"] = Decimal("0.00")
            group["current_usd"] = Decimal("0.00")
            group["allocation_pct"] = Decimal("0.00")
        fallback_key = ("unassigned", "unassigned")
        fallback = groups.setdefault(fallback_key, _new_allocation_group("unassigned", "Unassigned"))
        fallback["current_eur"] = current_eur
        fallback["current_usd"] = current_usd
        fallback["allocation_pct"] = None
        return

    largest = max(eligible, key=_positive_net_eur)
    for group in groups.values():
        group["current_eur"] = Decimal("0.00")
        group["current_usd"] = Decimal("0.00")
        group["allocation_pct"] = Decimal("0.00")
        positive_net = _positive_net_eur(group)
        if positive_net > 0:
            group["allocation_pct"] = positive_net / total_weight * Decimal("100")

    for currency, current in (("eur", current_eur), ("usd", current_usd)):
        allocated = Decimal("0.00")
        for group in eligible:
            share = _positive_net_eur(group) / total_weight
            amount = money(current * share)
            group[f"current_{currency}"] = amount
            allocated += amount
        largest[f"current_{currency}"] += current - allocated


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
    allocation_groups: dict[tuple[str, str], dict[str, Any]] = {}

    for row_index, flow in enumerate(rows):
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

        if str(flow.counterparty_type or "").strip().lower() == "person":
            normalized_name = _person_key(flow.counterparty_name)
            allocation_key = ("person", normalized_name)
            allocation_type = "person"
            allocation_name = str(flow.counterparty_name or "").strip()
        else:
            allocation_key = ("unassigned", "unassigned")
            allocation_type = "unassigned"
            allocation_name = "Unassigned"
        allocation = allocation_groups.setdefault(
            allocation_key,
            _new_allocation_group(allocation_type, allocation_name),
        )
        order = (flow.occurred_on, int(getattr(flow, "id", 0) or 0), row_index)
        if allocation["last_order"] is None or order >= allocation["last_order"]:
            allocation["counterparty_name"] = allocation_name
            allocation["last_order"] = order
        target = allocation["pending"] if is_pending else allocation["included"]
        _add_flow(target, flow)
        if is_pending:
            allocation["pending_count"] += 1

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

    _allocate_current(allocation_groups, current_eur, current_usd)
    allocations = []
    for group in sorted(
        allocation_groups.values(),
        key=lambda item: (
            item["counterparty_type"] == "unassigned",
            item["counterparty_name"].casefold(),
        ),
    ):
        allocations.append(
            {
                "counterparty_type": group["counterparty_type"],
                "counterparty_name": group["counterparty_name"],
                "allocation_pct": (
                    money_string(group["allocation_pct"])
                    if group["allocation_pct"] is not None
                    else None
                ),
                "eur": _currency_summary(
                    group["included"], "EUR", group["current_eur"], require_deposit=False
                ),
                "usd": _currency_summary(
                    group["included"], "USD", group["current_usd"], require_deposit=False
                ),
                "pending": {
                    "count": group["pending_count"],
                    "eur": _currency_summary(group["pending"], "EUR", None),
                    "usd": _currency_summary(group["pending"], "USD", None),
                },
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
        "allocations": allocations,
    }
