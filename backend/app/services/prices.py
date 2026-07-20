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
from sqlmodel import select

from ..db import get_session
from ..models import PriceSymbolMapping

log = logging.getLogger(__name__)

COINGECKO_BASE = os.getenv("COINGECKO_API_BASE", "https://api.coingecko.com/api/v3")

# Cache for coin list (symbol -> coin id)
_coin_list_cache: Dict[str, int | dict] = {"ts": 0, "data": {}}
_COIN_LIST_TTL = 24 * 3600

# Cache for DB-managed symbol mappings (symbol -> CoinGecko id)
_symbol_mapping_cache: Dict[str, int | dict] = {"ts": 0, "data": {}}
_SYMBOL_MAPPING_TTL = 60

# Price cache: symbol -> {ts, data}
_price_cache: Dict[str, dict] = {}
_PRICE_TTL = 60

# Contract-aware price cache: erc20:{chain}:{contract} -> {ts, data}
_contract_price_cache: Dict[str, dict] = {}
_contract_id_cache: Dict[str, int | bool | dict] = {"ts": 0, "data": {}, "loaded": False}
_CONTRACT_PLATFORM_IDS = {
    "ethereum": "ethereum",
    "base": "base",
    "polygon": "polygon-pos",
}

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


def clear_symbol_mapping_cache(symbol: str | None = None) -> None:
    """Clear mapping-dependent caches after admin mapping changes."""
    _symbol_mapping_cache["ts"] = 0
    _symbol_mapping_cache["data"] = {}
    if symbol:
        key = symbol.upper()
        _price_cache.pop(key, None)
        _icon_cache.pop(key, None)
        return
    _price_cache.clear()
    _icon_cache.clear()


def _load_symbol_mappings(reload: bool = False) -> Dict[str, str]:
    if (
        not reload
        and _now() - _symbol_mapping_cache["ts"] < _SYMBOL_MAPPING_TTL
        and _symbol_mapping_cache["data"]
    ):
        return _symbol_mapping_cache["data"]

    try:
        with get_session() as s:
            rows = s.exec(
                select(PriceSymbolMapping).where(
                    PriceSymbolMapping.provider == "coingecko",
                    PriceSymbolMapping.enabled == True,  # noqa: E712
                )
            ).all()
    except Exception as e:
        log.warning("failed to load price symbol mappings from DB: %s", e)
        return _symbol_mapping_cache["data"]

    mapping = {
        str(row.symbol or "").upper(): str(row.provider_id or "").strip()
        for row in rows
        if str(row.symbol or "").strip() and str(row.provider_id or "").strip()
    }
    _symbol_mapping_cache["ts"] = _now()
    _symbol_mapping_cache["data"] = mapping
    return mapping


def _symbol_to_id(symbol: str) -> str | None:
    override = _load_symbol_mappings().get(symbol.upper())
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


def _load_contract_id_map(reload: bool = False) -> Dict[str, str] | None:
    """Load CoinGecko IDs keyed by ``platform:contract``.

    The keyless contract-price endpoint can restrict requests to one address.
    Resolving contracts through the daily coin list lets the normal bulk price
    endpoint remain efficient while preserving contract-based identity.
    """
    if (
        not reload
        and bool(_contract_id_cache["loaded"])
        and _now() - float(_contract_id_cache["ts"]) < _COIN_LIST_TTL
    ):
        return _contract_id_cache["data"]  # type: ignore[return-value]

    url = f"{COINGECKO_BASE}/coins/list"
    attempts = 0
    backoff = 1
    while attempts < 4:
        try:
            with httpx.Client(timeout=30) as cli:
                response = cli.get(url, params={"include_platform": "true"})
                if response.status_code == 429:
                    attempts += 1
                    log.warning("CoinGecko contract map rate limited, sleeping %s seconds", backoff)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                response.raise_for_status()
                rows = response.json()
                mapping: Dict[str, str] = {}
                supported_platforms = set(_CONTRACT_PLATFORM_IDS.values())
                for row in rows if isinstance(rows, list) else []:
                    coin_id = str(row.get("id") or "").strip()
                    if not coin_id:
                        continue
                    platforms = row.get("platforms") or {}
                    if not isinstance(platforms, dict):
                        continue
                    for platform, raw_contract in platforms.items():
                        contract = str(raw_contract or "").strip().lower()
                        if platform in supported_platforms and contract:
                            mapping[f"{platform}:{contract}"] = coin_id
                _contract_id_cache["ts"] = _now()
                _contract_id_cache["data"] = mapping
                _contract_id_cache["loaded"] = True
                return mapping
        except Exception as exc:
            attempts += 1
            log.warning(
                "error fetching CoinGecko contract map (attempt %s): %s",
                attempts,
                exc,
            )
            if attempts < 4:
                time.sleep(backoff)
                backoff *= 2

    log.error("failed to fetch CoinGecko contract map after retries")
    cached = _contract_id_cache.get("data")
    if bool(_contract_id_cache.get("loaded")) and isinstance(cached, dict):
        return cached  # type: ignore[return-value]
    return None


def fetch_evm_token_prices(tokens: List[dict]) -> Dict[str, dict]:
    """Return ERC-20 prices keyed by contract-aware ``price_key``.

    Tokens absent from CoinGecko, unsupported chains and provider failures are
    explicitly unpriced. Symbol pricing is never used as a fallback.
    """
    now = _now()
    out: Dict[str, dict] = {}
    pending: Dict[str, tuple[str, str]] = {}

    for token in tokens:
        chain = str(token.get("chain") or "").strip().lower()
        contract = str(token.get("contract_address") or token.get("contract") or "").strip().lower()
        price_key = str(token.get("price_key") or "").strip()
        if not price_key and chain and contract:
            price_key = f"erc20:{chain}:{contract}"
        if not price_key:
            continue

        cached = _contract_price_cache.get(price_key)
        if cached and now - cached["ts"] < _PRICE_TTL:
            out[price_key] = cached["data"].copy()
            continue

        if chain not in _CONTRACT_PLATFORM_IDS or not contract:
            entry = {
                "price_eur": 0.0,
                "price_usd": 0.0,
                "ts": now,
                "source": "unsupported_contract_chain",
            }
            out[price_key] = entry
            _contract_price_cache[price_key] = {"ts": now, "data": entry}
            continue
        pending[price_key] = (_CONTRACT_PLATFORM_IDS[chain], contract)

    if not pending:
        return out

    contract_ids = _load_contract_id_map()
    if contract_ids is None:
        for price_key in pending:
            entry = {
                "price_eur": 0.0,
                "price_usd": 0.0,
                "ts": now,
                "source": "coingecko_contract_error",
            }
            out[price_key] = entry
            _contract_price_cache[price_key] = {"ts": now, "data": entry}
        return out

    price_keys_by_id: Dict[str, List[str]] = {}
    for price_key, (platform, contract) in pending.items():
        coin_id = contract_ids.get(f"{platform}:{contract}")
        if coin_id:
            price_keys_by_id.setdefault(coin_id, []).append(price_key)
            continue
        entry = {
            "price_eur": 0.0,
            "price_usd": 0.0,
            "ts": now,
            "source": "coingecko_contract_missing",
        }
        out[price_key] = entry
        _contract_price_cache[price_key] = {"ts": now, "data": entry}

    if price_keys_by_id:
        price_response = _fetch_simple_price(list(price_keys_by_id))
        provider_failed = not price_response
        for coin_id, price_keys in price_keys_by_id.items():
            data = price_response.get(coin_id)
            for price_key in price_keys:
                if isinstance(data, dict):
                    entry = {
                        "price_eur": float(data.get("eur", 0.0) or 0.0),
                        "price_usd": float(data.get("usd", 0.0) or 0.0),
                        "ts": now,
                        "source": "coingecko_contract",
                    }
                else:
                    entry = {
                        "price_eur": 0.0,
                        "price_usd": 0.0,
                        "ts": now,
                        "source": "coingecko_contract_error" if provider_failed else "coingecko_contract_missing",
                    }
                out[price_key] = entry
                _contract_price_cache[price_key] = {"ts": now, "data": entry}

    return out


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
