"""CoinGecko price connector with simple in-memory caching and retries.

This module provides `fetch_prices(symbols)` which returns a mapping
symbol -> {price_eur, price_usd, ts, source}. It uses CoinGecko's
`/coins/list` to map symbols to CoinGecko ids and `/simple/price` to
fetch EUR/USD prices.

Notes:
- In-memory cache (process-local) with TTL is used to reduce requests.
- Basic retry/backoff on network errors and 429 responses.
"""

import logging
import os
import time
from typing import Dict, List

import httpx

log = logging.getLogger(__name__)

COINGECKO_BASE = os.getenv("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3")

# Symbol overrides for ambiguous CoinGecko symbols.
# Example: ONE should resolve to Harmony.
SYMBOL_ID_OVERRIDES: Dict[str, str] = {
    "BTC": "bitcoin",
    "GUN": "gunz",
    "GPS": "goplus-security",
    "ONE": "harmony",
    "XLM": "stellar",
    "XRP": "ripple",
    "TRX": "tron",
}

# Cache for coin list (symbol -> coin id)
_coin_list_cache: Dict[str, int | dict] = {"ts": 0, "data": {}}
_COIN_LIST_TTL = 24 * 3600

# Price cache: symbol -> {ts, data}
_price_cache: Dict[str, dict] = {}
_PRICE_TTL = 60

# Icon cache: symbol -> {ts, data}
_icon_cache: Dict[str, dict] = {}
_ICON_TTL = 12 * 3600


def _now() -> float:
    return time.time()


def _load_coin_list(reload: bool = False) -> Dict[str, str]:
    """Load coin list from CoinGecko and cache mapping symbol -> id."""
    if (
        not reload
        and _now() - _coin_list_cache["ts"] < _COIN_LIST_TTL
        and _coin_list_cache["data"]
    ):
        return _coin_list_cache["data"]

    url = f"{COINGECKO_BASE}/coins/list"
    try:
        with httpx.Client(timeout=10) as cli:
            r = cli.get(url)
            r.raise_for_status()
            coins = r.json()
    except Exception as e:
        log.warning("failed to fetch coin list from CoinGecko: %s", e)
        # fallback to whatever we have cached (possibly empty)
        return _coin_list_cache["data"]

    mapping: Dict[str, str] = {}
    for c in coins:
        # coin fields: id, symbol, name
        sym = c.get("symbol", "").lower()
        # keep the first occurrence for a symbol
        if sym and sym not in mapping:
            mapping[sym] = c.get("id")

    _coin_list_cache["ts"] = _now()
    _coin_list_cache["data"] = mapping
    return mapping


def _symbol_to_id(symbol: str) -> str | None:
    override = SYMBOL_ID_OVERRIDES.get(symbol.upper())
    if override:
        return override
    mapping = _load_coin_list()
    return mapping.get(symbol.lower())


def _fetch_simple_price(ids: List[str]) -> Dict[str, dict]:
    """Call /simple/price for given coin ids.

    Returns CoinGecko response dict keyed by coin id.
    """
    if not ids:
        return {}

    url = f"{COINGECKO_BASE}/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "eur,usd"}
    attempts = 0
    backoff = 1
    while attempts < 4:
        try:
            with httpx.Client(timeout=10) as cli:
                r = cli.get(url, params=params)
                if r.status_code == 429:
                    attempts += 1
                    log.warning("CoinGecko rate limited, sleeping %s seconds", backoff)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                r.raise_for_status()
                return r.json()
        except Exception as e:
            attempts += 1
            log.warning(
                "error fetching prices from CoinGecko (attempt %s): %s", attempts, e
            )
            time.sleep(backoff)
            backoff *= 2

    log.error("failed to fetch prices from CoinGecko after retries")
    return {}


def _fetch_coin_markets(ids: List[str]) -> Dict[str, dict]:
    """Call /coins/markets for coin ids and return dict keyed by id."""
    if not ids:
        return {}

    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "per_page": max(len(ids), 1),
        "page": 1,
        "sparkline": "false",
    }
    attempts = 0
    backoff = 1
    while attempts < 4:
        try:
            with httpx.Client(timeout=10) as cli:
                r = cli.get(url, params=params)
                if r.status_code == 429:
                    attempts += 1
                    log.warning("CoinGecko rate limited (icons), sleeping %s seconds", backoff)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                r.raise_for_status()
                rows = r.json()
                return {str(row.get("id")): row for row in rows}
        except Exception as e:
            attempts += 1
            log.warning(
                "error fetching market/icon data from CoinGecko (attempt %s): %s",
                attempts,
                e,
            )
            time.sleep(backoff)
            backoff *= 2

    log.error("failed to fetch market/icon data from CoinGecko after retries")
    return {}


def fetch_prices(symbols: List[str]) -> Dict[str, dict]:
    """Fetch prices for a list of symbols.

    Returns mapping symbol -> {price_eur, price_usd, ts, source}
    """
    out: Dict[str, dict] = {}
    now = _now()

    to_query_ids: List[str] = []
    symbol_to_id: Dict[str, str] = {}

    # First, serve from cache when valid
    for s in symbols:
        cached = _price_cache.get(s.upper())
        if cached and now - cached["ts"] < _PRICE_TTL:
            out[s] = cached["data"].copy()
            continue

        cid = _symbol_to_id(s)
        if cid:
            symbol_to_id[s] = cid
            to_query_ids.append(cid)
        else:
            # no mapping found; return 0 prices for now
            out[s] = {"price_eur": 0.0, "price_usd": 0.0, "ts": now, "source": "none"}

    # Query CoinGecko for ids (deduplicate ids)
    ids = list(dict.fromkeys(to_query_ids))
    if ids:
        cg_resp = _fetch_simple_price(ids)
        # map back to symbols
        for sym, cid in symbol_to_id.items():
            data = cg_resp.get(cid)
            if data:
                entry = {
                    "price_eur": float(data.get("eur", 0.0)),
                    "price_usd": float(data.get("usd", 0.0)),
                    "ts": now,
                    "source": "coingecko",
                }
            else:
                entry = {
                    "price_eur": 0.0,
                    "price_usd": 0.0,
                    "ts": now,
                    "source": "coingecko_missing",
                }

            out[sym] = entry
            # update cache by UPPER symbol key
            _price_cache[sym.upper()] = {"ts": now, "data": entry}

    return out


def fetch_icon_urls(symbols: List[str]) -> Dict[str, str]:
    """Fetch icon URLs for symbols using CoinGecko ids.

    Returns mapping symbol -> image URL.
    """
    out: Dict[str, str] = {}
    now = _now()
    symbol_to_id: Dict[str, str] = {}

    for sym in symbols:
        key = sym.upper()
        cached = _icon_cache.get(key)
        if cached and now - cached["ts"] < _ICON_TTL:
            icon_url = str(cached.get("data") or "")
            if icon_url:
                out[key] = icon_url
            continue

        cid = _symbol_to_id(sym)
        if cid:
            symbol_to_id[key] = cid

    ids = list(dict.fromkeys(symbol_to_id.values()))
    if ids:
        market_data = _fetch_coin_markets(ids)
        for sym, cid in symbol_to_id.items():
            row = market_data.get(cid) or {}
            icon_url = str(row.get("image") or "")
            if icon_url:
                out[sym] = icon_url
            _icon_cache[sym] = {"ts": now, "data": icon_url}

    return out
