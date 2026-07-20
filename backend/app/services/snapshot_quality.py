"""Conservative, read-only quality checks for historical portfolio snapshots."""

from __future__ import annotations

import json
import math
from typing import Any


MAX_PLAUSIBLE_NATIVE_ETH_QUANTITY = 1_000_000.0
MAX_PLAUSIBLE_PORTFOLIO_TOTAL = 1_000_000_000_000_000.0


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return float("nan")


def _metadata(snapshot: Any) -> dict[str, Any]:
    raw = getattr(snapshot, "meta", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def audit_snapshot(snapshot: Any) -> dict[str, Any] | None:
    """Return conservative anomaly details, or None for a plausible snapshot."""
    reasons: list[str] = []
    totals = [
        _number(getattr(snapshot, "total_eur", 0.0)),
        _number(getattr(snapshot, "total_usd", 0.0)),
    ]
    if any(not math.isfinite(total) for total in totals):
        reasons.append("non_finite_total")
    elif any(abs(total) > MAX_PLAUSIBLE_PORTFOLIO_TOTAL for total in totals):
        reasons.append("total_exceeds_safety_limit")

    eth_quantity = 0.0
    meta = _metadata(snapshot)
    for coin in meta.get("coins") or []:
        if not isinstance(coin, dict):
            continue
        symbol = str(coin.get("key") or coin.get("name") or "").strip().upper()
        if symbol != "ETH":
            continue
        eth_quantity = _number(coin.get("qty"))
        if not math.isfinite(eth_quantity) or abs(eth_quantity) > MAX_PLAUSIBLE_NATIVE_ETH_QUANTITY:
            reasons.append("implausible_eth_quantity")
        break

    if not reasons:
        return None
    suggested_reason = (
        "erc20_native_symbol_spoof"
        if "implausible_eth_quantity" in reasons
        else "implausible_snapshot_total"
    )
    return {
        "detected_reasons": reasons,
        "suggested_reason": suggested_reason,
        "eth_quantity": eth_quantity,
    }

