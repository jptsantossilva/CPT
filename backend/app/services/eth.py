"""Ethereum wallet service via JSON-RPC.

Current behavior:
- Always tries to fetch native ETH balance via `eth_getBalance`.
- Optionally fetches ERC-20 balances via Alchemy methods when the configured
  RPC endpoint supports them.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List

import httpx

from ..config import settings
from ..wallet_chains import normalize_wallet_chain

log = logging.getLogger(__name__)

_CHAIN_METADATA = {
    "ethereum": {"chain_id": 1, "native_symbol": "ETH", "native_name": "Ether"},
    "base": {"chain_id": 8453, "native_symbol": "ETH", "native_name": "Ether"},
    "polygon": {"chain_id": 137, "native_symbol": "POL", "native_name": "Polygon"},
}


def _is_eth_address(value: str) -> bool:
    s = value.strip()
    return len(s) == 42 and s.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in s[2:])


def _rpc_call(
    rpc_url: str,
    method: str,
    params: list[Any],
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    if client is not None:
        resp = client.post(rpc_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    else:
        with httpx.Client(timeout=timeout) as cli:
            resp = cli.post(rpc_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

    if "error" in data:
        raise RuntimeError(f"rpc error for {method}: {data['error']}")
    return data.get("result")


def _hex_to_int(value: str | None) -> int:
    if not value:
        return 0
    return int(value, 16)


def _chain_metadata(chain: str) -> dict[str, int | str]:
    normalized_chain = normalize_wallet_chain(chain)
    meta = _CHAIN_METADATA.get(normalized_chain)
    if not meta:
        raise ValueError(f"unsupported wallet chain metadata: {normalized_chain}")
    return meta


def _validate_rpc_chain_id(
    rpc_url: str,
    chain: str,
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> bool:
    meta = _chain_metadata(chain)
    expected_chain_id = int(meta["chain_id"])
    chain_id_hex = _rpc_call(
        rpc_url,
        "eth_chainId",
        [],
        timeout=timeout,
        client=client,
    )
    actual_chain_id = _hex_to_int(chain_id_hex)
    if actual_chain_id != expected_chain_id:
        log.warning(
            "rpc chain mismatch for %s: expected=%s got=%s",
            chain,
            expected_chain_id,
            actual_chain_id,
        )
        return False
    return True


def _fetch_alchemy_erc20_balances(
    rpc_url: str,
    address: str,
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> List[dict]:
    """Fetch ERC-20 balances with Alchemy-specific methods."""
    out: List[dict] = []
    # Prefer all ERC-20 balances. Fallback to DEFAULT_TOKENS for compatibility.
    try:
        result = _rpc_call(
            rpc_url,
            "alchemy_getTokenBalances",
            [address, "erc20"],
            timeout=timeout,
            client=client,
        ) or {}
    except Exception:
        result = _rpc_call(
            rpc_url,
            "alchemy_getTokenBalances",
            [address, "DEFAULT_TOKENS"],
            timeout=timeout,
            client=client,
        ) or {}

    rows = result.get("tokenBalances") or []
    for row in rows:
        contract = str(row.get("contractAddress") or "").strip().lower()
        raw_balance = row.get("tokenBalance")
        if not contract or not raw_balance:
            continue
        raw = _hex_to_int(raw_balance)
        if raw <= 0:
            continue

        try:
            meta = _rpc_call(
                rpc_url,
                "alchemy_getTokenMetadata",
                [contract],
                timeout=timeout,
                client=client,
            ) or {}
        except Exception:
            log.warning("failed to fetch token metadata for contract=%s", contract)
            continue

        symbol = str(meta.get("symbol") or "").upper().strip()
        decimals = meta.get("decimals")
        if not symbol or decimals is None:
            continue

        try:
            decimals_int = int(decimals)
        except (TypeError, ValueError):
            continue
        if decimals_int < 0:
            continue

        balance = raw / (10**decimals_int)
        if balance <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "name": str(meta.get("name") or "").strip() or None,
                "balance": balance,
                "asset_kind": "erc20",
                "contract": contract,
            }
        )
    return out


def fetch_wallet_balances(
    address: str,
    *,
    chain: str = "ethereum",
    rpc_url: str | None = None,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> List[dict]:
    """Fetch balances for a wallet address.

    Returns list of dicts like:
    - {"symbol": "ETH", "balance": 0.42}
    - {"symbol": "USDC", "balance": 120.5}
    """
    wallet = address.strip()
    if not _is_eth_address(wallet):
        log.warning("invalid ethereum wallet address: %s", address)
        return []

    normalized_chain = normalize_wallet_chain(chain)
    endpoint = rpc_url or rpc_url_for_chain(normalized_chain)
    if not endpoint:
        log.warning(
            "%s RPC URL is not configured; skipping wallet sync for address=%s",
            normalized_chain,
            wallet,
        )
        return []

    try:
        if not _validate_rpc_chain_id(endpoint, normalized_chain, timeout=timeout, client=client):
            return []
    except Exception:
        log.exception("failed to validate rpc chain id for chain=%s", normalized_chain)
        return []

    meta = _chain_metadata(normalized_chain)
    out: List[dict] = []

    try:
        raw_wei_hex = _rpc_call(
            endpoint,
            "eth_getBalance",
            [wallet, "latest"],
            timeout=timeout,
            client=client,
        )
        wei = _hex_to_int(raw_wei_hex)
        eth_balance = wei / 1_000_000_000_000_000_000
        if eth_balance > 0:
            out.append(
                {
                    "symbol": str(meta["native_symbol"]),
                    "name": str(meta["native_name"]),
                    "contract": "native",
                    "asset_kind": "native",
                    "balance": eth_balance,
                }
            )
    except Exception:
        log.exception("failed fetching ETH balance for wallet=%s", wallet)
        return []

    # Optional ERC-20 fetch (works on Alchemy RPC endpoints)
    if "alchemy" in endpoint.lower():
        try:
            out.extend(_fetch_alchemy_erc20_balances(endpoint, wallet, timeout=timeout, client=client))
        except Exception:
            log.exception("failed fetching ERC-20 balances for wallet=%s", wallet)

    return out


def rpc_url_for_chain(chain: str) -> str | None:
    normalized_chain = normalize_wallet_chain(chain)
    if normalized_chain == "ethereum":
        return getattr(settings, "ETH_RPC_URL", None) or os.getenv("ETH_RPC_URL")
    if normalized_chain == "base":
        return getattr(settings, "BASE_RPC_URL", None) or os.getenv("BASE_RPC_URL")
    if normalized_chain == "polygon":
        return getattr(settings, "POLYGON_RPC_URL", None) or os.getenv("POLYGON_RPC_URL")
    return None
