"""Bitcoin wallet balance service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings
from ..wallet_chains import is_bitcoin_address

log = logging.getLogger(__name__)


def _safe_int(data: dict[str, Any], key: str) -> int:
    try:
        return int(data.get(key) or 0)
    except Exception:
        return 0


def fetch_wallet_balances(
    address: str,
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch BTC balance for a Bitcoin address.

    Returns a list with one row like {"symbol": "BTC", "balance": 0.01} when
    the balance is positive, otherwise returns an empty list.
    """
    wallet = (address or "").strip()
    if not is_bitcoin_address(wallet):
        log.warning("invalid bitcoin wallet address: %s", address)
        return []

    base_url = (
        getattr(settings, "BTC_API_BASE", None)
        or "https://blockstream.info/api"
    ).rstrip("/")
    url = f"{base_url}/address/{wallet}"

    try:
        if client is not None:
            resp = client.get(url)
        else:
            with httpx.Client(timeout=timeout) as cli:
                resp = cli.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        log.exception("failed to fetch BTC balance for wallet=%s", wallet)
        return []

    chain_stats = data.get("chain_stats") or {}
    mempool_stats = data.get("mempool_stats") or {}

    funded = _safe_int(chain_stats, "funded_txo_sum") + _safe_int(mempool_stats, "funded_txo_sum")
    spent = _safe_int(chain_stats, "spent_txo_sum") + _safe_int(mempool_stats, "spent_txo_sum")
    satoshis = max(0, funded - spent)
    if satoshis <= 0:
        return []

    btc = satoshis / 100_000_000
    return [{"symbol": "BTC", "name": "Bitcoin", "balance": btc}]

