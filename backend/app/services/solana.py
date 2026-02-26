"""Solana wallet balance service."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from ..config import settings
from ..wallet_chains import is_solana_address

log = logging.getLogger(__name__)

_SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_SPL_TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_TOKEN_LIST_CACHE: dict[str, Any] = {"ts": 0.0, "data": {}}
_TOKEN_LIST_TTL = 6 * 3600
_TOKEN_BY_MINT_CACHE: dict[str, dict[str, Any]] = {}
_TOKEN_BY_MINT_TTL = 6 * 3600


def _now() -> float:
    return time.time()


def _token_list_urls() -> list[str]:
    raw = (
        str(getattr(settings, "SOLANA_TOKEN_LIST_URL", "") or "")
        or str(os.getenv("SOLANA_TOKEN_LIST_URL") or "")
    )
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    fallbacks = [
        "https://tokens.jup.ag/tokens",
        "https://cache.jup.ag/tokens",
        "https://token.jup.ag/all",
    ]
    for url in fallbacks:
        if url not in urls:
            urls.append(url)
    return urls


def _parse_token_rows(rows: Any) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    candidates = rows
    if isinstance(rows, dict):
        if isinstance(rows.get("tokens"), list):
            candidates = rows.get("tokens")
        else:
            candidates = []
    if not isinstance(candidates, list):
        return out
    for row in candidates:
        if not isinstance(row, dict):
            continue
        mint = str(row.get("address") or "").strip().lower()
        symbol = str(row.get("symbol") or "").strip().upper()
        name = str(row.get("name") or "").strip() or None
        if mint and symbol:
            out[mint] = {"symbol": symbol, "name": name}
    return out


def _load_token_registry(*, timeout: float = 12.0) -> dict[str, dict[str, str | None]]:
    cached = _TOKEN_LIST_CACHE.get("data") or {}
    if cached and (_now() - float(_TOKEN_LIST_CACHE.get("ts") or 0.0)) < _TOKEN_LIST_TTL:
        return cached

    urls = _token_list_urls()
    for url in urls:
        try:
            with httpx.Client(timeout=timeout) as cli:
                resp = cli.get(url)
                resp.raise_for_status()
                parsed = _parse_token_rows(resp.json())
                if parsed:
                    _TOKEN_LIST_CACHE["ts"] = _now()
                    _TOKEN_LIST_CACHE["data"] = parsed
                    return parsed
        except Exception:
            log.warning("failed loading Solana token registry from %s", url)
            continue
    return cached


def _fetch_token_by_mint(mint: str, *, timeout: float = 12.0) -> tuple[str, str | None] | None:
    key = mint.lower()
    cached = _TOKEN_BY_MINT_CACHE.get(key)
    if cached and (_now() - float(cached.get("ts") or 0.0)) < _TOKEN_BY_MINT_TTL:
        symbol = str(cached.get("symbol") or "").strip().upper()
        name = cached.get("name")
        if symbol:
            return symbol, name if isinstance(name, str) else None
        return None

    template = (
        str(getattr(settings, "SOLANA_TOKEN_LOOKUP_URL_TEMPLATE", "") or "")
        or str(os.getenv("SOLANA_TOKEN_LOOKUP_URL_TEMPLATE") or "")
        or "https://lite-api.jup.ag/tokens/v1/token/{mint}"
    )
    url = template.replace("{mint}", mint)
    try:
        with httpx.Client(timeout=timeout) as cli:
            resp = cli.get(url)
            resp.raise_for_status()
            row = resp.json()
    except Exception:
        log.warning("failed Solana single token lookup for mint=%s", mint)
        return None

    if not isinstance(row, dict):
        return None
    symbol = str(row.get("symbol") or "").strip().upper()
    name = str(row.get("name") or "").strip() or None
    if not symbol:
        return None
    _TOKEN_BY_MINT_CACHE[key] = {"ts": _now(), "symbol": symbol, "name": name}
    return symbol, name


def _rpc_call(
    endpoint: str,
    method: str,
    params: list[Any],
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    if client is not None:
        resp = client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
    else:
        with httpx.Client(timeout=timeout) as cli:
            resp = cli.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"solana rpc error for {method}: {data.get('error')}")
    if not isinstance(data, dict):
        return {}
    return data.get("result")


def _token_symbol_and_name(
    mint: str,
    registry: dict[str, dict[str, str | None]] | None = None,
    *,
    timeout: float = 12.0,
) -> tuple[str, str | None]:
    m = (mint or "").strip()
    if not m:
        return "", None
    lookup_key = m.lower()
    if registry:
        reg = registry.get(lookup_key)
        if isinstance(reg, dict):
            symbol = str(reg.get("symbol") or "").strip().upper()
            if symbol:
                return symbol, reg.get("name")
    by_mint = _fetch_token_by_mint(m, timeout=timeout)
    if by_mint:
        return by_mint
    return m, None


def _fetch_spl_token_balances(
    endpoint: str,
    wallet: str,
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    totals_by_symbol: dict[str, float] = {}
    name_by_symbol: dict[str, str | None] = {}
    token_registry = _load_token_registry(timeout=timeout)

    def _collect_for_program(program_id: str) -> None:
        result = _rpc_call(
            endpoint,
            "getTokenAccountsByOwner",
            [
                wallet,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ],
            timeout=timeout,
            client=client,
        ) or {}
        rows = result.get("value") if isinstance(result, dict) else []
        if not isinstance(rows, list):
            return
        for row in rows:
            info = (
                (((row or {}).get("account") or {}).get("data") or {}).get("parsed") or {}
            ).get("info") or {}
            mint = str(info.get("mint") or "").strip()
            token_amount = info.get("tokenAmount") or {}
            if not mint or not isinstance(token_amount, dict):
                continue
            decimals = token_amount.get("decimals")
            amount_raw = str(token_amount.get("amount") or "").strip()
            if decimals is None or not amount_raw:
                continue
            try:
                decimals_int = int(decimals)
                amount_int = int(amount_raw)
            except (TypeError, ValueError):
                continue
            if decimals_int < 0 or amount_int <= 0:
                continue
            balance = amount_int / (10**decimals_int)
            if balance <= 0:
                continue
            symbol, name = _token_symbol_and_name(mint, token_registry, timeout=timeout)
            if not symbol:
                continue
            totals_by_symbol[symbol] = totals_by_symbol.get(symbol, 0.0) + balance
            if name and symbol not in name_by_symbol:
                name_by_symbol[symbol] = name

    for program_id in (_SPL_TOKEN_PROGRAM_ID, _SPL_TOKEN_2022_PROGRAM_ID):
        try:
            _collect_for_program(program_id)
        except Exception:
            log.warning(
                "failed SPL token account lookup endpoint=%s wallet=%s program=%s",
                endpoint,
                wallet,
                program_id,
            )

    out: list[dict] = []
    for symbol in sorted(totals_by_symbol.keys()):
        balance = totals_by_symbol.get(symbol, 0.0)
        if balance <= 0:
            continue
        row = {"symbol": symbol, "balance": balance}
        if name_by_symbol.get(symbol):
            row["name"] = name_by_symbol[symbol]
        out.append(row)
    return out


def fetch_wallet_balances(
    address: str,
    *,
    rpc_url: str | None = None,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch SOL and SPL token balances for a Solana address."""
    wallet = (address or "").strip()
    if not is_solana_address(wallet):
        log.warning("invalid solana wallet address: %s", address)
        return []

    primary_endpoint = (
        rpc_url
        or getattr(settings, "SOLANA_RPC_URL", None)
        or os.getenv("SOLANA_RPC_URL")
    )
    fallback_endpoint = (
        getattr(settings, "SOLANA_RPC_FALLBACK_URL", None)
        or os.getenv("SOLANA_RPC_FALLBACK_URL")
        or "https://api.mainnet.solana.com"
    )
    endpoints = [str(e).strip() for e in (primary_endpoint, fallback_endpoint) if str(e or "").strip()]
    # Deduplicate while preserving order.
    endpoints = list(dict.fromkeys(endpoints))

    out: list[dict] = []
    for endpoint in endpoints:
        try:
            native_result = _rpc_call(
                endpoint,
                "getBalance",
                [wallet],
                timeout=timeout,
                client=client,
            ) or {}
            lamports = int((native_result if isinstance(native_result, dict) else {}).get("value") or 0)
            if lamports > 0:
                sol = lamports / 1_000_000_000
                out.append({"symbol": "SOL", "name": "Solana", "balance": sol})

            out.extend(
                _fetch_spl_token_balances(
                    endpoint,
                    wallet,
                    timeout=timeout,
                    client=client,
                )
            )
            break
        except Exception:
            log.warning("failed SOL RPC call endpoint=%s wallet=%s", endpoint, wallet)
            continue

    return out
