from datetime import datetime, timedelta
import json
from typing import Any


_PERIODS: list[tuple[str, timedelta | None]] = [
    ("1h", timedelta(hours=1)),
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
    ("14d", timedelta(days=14)),
    ("30d", timedelta(days=30)),
    ("1y", timedelta(days=365)),
    ("max", None),
]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100.0


def _find_baseline_before_or_equal(rows: list[Any], cutoff: datetime) -> Any | None:
    candidate = None
    for row in rows:
        ts = getattr(row, "timestamp", None)
        if not isinstance(ts, datetime):
            continue
        if ts <= cutoff:
            candidate = row
        else:
            break
    return candidate


def compute_variations(rows: list[Any], now: datetime | None = None) -> dict[str, Any]:
    """Compute portfolio total variations for predefined periods.

    Expects rows sorted by timestamp ascending.
    """
    if not rows:
        return {
            "latest": None,
            "periods": {name: None for name, _ in _PERIODS},
        }

    if now is None:
        now = datetime.utcnow()

    latest = rows[-1]
    latest_eur = _to_float(getattr(latest, "total_eur", 0.0))
    latest_usd = _to_float(getattr(latest, "total_usd", 0.0))

    out_periods: dict[str, Any] = {}
    oldest = rows[0]

    for name, delta in _PERIODS:
        if delta is None:
            baseline = oldest
        else:
            cutoff = now - delta
            baseline = _find_baseline_before_or_equal(rows, cutoff)
            if baseline is None:
                out_periods[name] = None
                continue

        base_eur = _to_float(getattr(baseline, "total_eur", 0.0))
        base_usd = _to_float(getattr(baseline, "total_usd", 0.0))

        out_periods[name] = {
            "baseline_timestamp": getattr(baseline, "timestamp", None),
            "baseline_total_eur": base_eur,
            "baseline_total_usd": base_usd,
            "change_pct_eur": _pct_change(latest_eur, base_eur),
            "change_pct_usd": _pct_change(latest_usd, base_usd),
            "change_abs_eur": latest_eur - base_eur,
            "change_abs_usd": latest_usd - base_usd,
        }

    return {
        "latest": {
            "timestamp": getattr(latest, "timestamp", None),
            "total_eur": latest_eur,
            "total_usd": latest_usd,
        },
        "periods": out_periods,
    }


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _snapshot_meta(snapshot: Any) -> dict[str, Any]:
    raw = getattr(snapshot, "meta", None)
    if not raw:
        return {}
    try:
        out = json.loads(raw)
    except Exception:
        return {}
    return out if isinstance(out, dict) else {}


def build_portfolio_history(rows: list[Any]) -> dict[str, Any]:
    """Build chart-ready daily history from snapshots (ascending by timestamp)."""
    points: list[dict[str, Any]] = []
    coin_labels: dict[str, str] = {}
    nft_labels: dict[str, str] = {}

    for row in rows:
        meta = _snapshot_meta(row)
        totals = meta.get("totals") if isinstance(meta.get("totals"), dict) else {}

        coins_map: dict[str, dict[str, float]] = {}
        for coin in meta.get("coins") or []:
            if not isinstance(coin, dict):
                continue
            key = str(coin.get("key") or coin.get("name") or "").strip()
            if not key:
                continue
            name = str(coin.get("name") or key).strip()
            coin_labels[key] = name
            coins_map[key] = {"eur": _safe_float(coin.get("eur")), "usd": _safe_float(coin.get("usd"))}

        nfts_map: dict[str, dict[str, float]] = {}
        for nft in meta.get("nfts") or []:
            if not isinstance(nft, dict):
                continue
            key = str(nft.get("key") or "").strip()
            if not key:
                continue
            name = str(nft.get("name") or key).strip()
            nft_labels[key] = name
            nfts_map[key] = {"eur": _safe_float(nft.get("eur")), "usd": _safe_float(nft.get("usd"))}

        coins_eur = _safe_float(totals.get("coins_eur", getattr(row, "total_eur", 0.0)))
        coins_usd = _safe_float(totals.get("coins_usd", getattr(row, "total_usd", 0.0)))
        nfts_eur = _safe_float(totals.get("nfts_eur", 0.0))
        nfts_usd = _safe_float(totals.get("nfts_usd", 0.0))
        portfolio_eur = _safe_float(totals.get("portfolio_eur", coins_eur + nfts_eur))
        portfolio_usd = _safe_float(totals.get("portfolio_usd", coins_usd + nfts_usd))

        points.append(
            {
                "timestamp": getattr(row, "timestamp", None),
                "totals": {
                    "coins_eur": coins_eur,
                    "coins_usd": coins_usd,
                    "nfts_eur": nfts_eur,
                    "nfts_usd": nfts_usd,
                    "portfolio_eur": portfolio_eur,
                    "portfolio_usd": portfolio_usd,
                },
                "coins": coins_map,
                "nfts": nfts_map,
            }
        )

    return {
        "points": points,
        "coin_labels": coin_labels,
        "nft_labels": nft_labels,
    }
