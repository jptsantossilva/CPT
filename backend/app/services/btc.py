"""Bitcoin wallet balance service."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from ..config import settings
from ..wallet_chains import (
    is_bitcoin_address,
    is_bitcoin_extended_public_key,
    is_bitcoin_mainnet_identifier,
)

log = logging.getLogger(__name__)
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BLOCKCHAIR_API_BASE = "https://api.blockchair.com"
_HASKOIN_API_BASE = "https://api.blockchain.info/haskoin-store"
_SLIP132_TO_XPUB = {
    # BIP49 mainnet public
    bytes.fromhex("049d7cb2"): bytes.fromhex("0488b21e"),  # ypub -> xpub
    # BIP84 mainnet public
    bytes.fromhex("04b24746"): bytes.fromhex("0488b21e"),  # zpub -> xpub
}


def _safe_int(data: dict[str, Any], key: str) -> int:
    try:
        return int(data.get(key) or 0)
    except Exception:
        return 0


def _base58check_decode(value: str) -> bytes:
    n = 0
    for ch in value:
        try:
            n = n * 58 + _BASE58_ALPHABET.index(ch)
        except ValueError as exc:
            raise ValueError("invalid base58 character") from exc
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading_zeroes = len(value) - len(value.lstrip("1"))
    full = (b"\x00" * leading_zeroes) + raw
    if len(full) < 5:
        raise ValueError("invalid base58check length")
    payload, checksum = full[:-4], full[-4:]
    expected = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if checksum != expected:
        raise ValueError("invalid base58check checksum")
    return payload


def _base58check_encode(payload: bytes) -> str:
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    data = payload + checksum
    n = int.from_bytes(data, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _BASE58_ALPHABET[rem] + out
    leading_zeroes = len(data) - len(data.lstrip(b"\x00"))
    return ("1" * leading_zeroes) + (out or "1")


def _normalize_mainnet_extended_pubkey(identifier: str) -> str:
    """Convert ypub/zpub to xpub for APIs that only support xpub endpoints."""
    raw = (identifier or "").strip()
    if not raw.startswith(("ypub", "zpub")):
        return raw
    payload = _base58check_decode(raw)
    if len(payload) < 4:
        raise ValueError("invalid extended pubkey")
    src_prefix = payload[:4]
    target_prefix = _SLIP132_TO_XPUB.get(src_prefix)
    if not target_prefix:
        raise ValueError("unsupported extended pubkey prefix")
    return _base58check_encode(target_prefix + payload[4:])


def _derive_btc_mainnet_receive_addresses(
    identifier: str,
    *,
    max_scan: int = 120,
) -> list[str]:
    """Derive external(receive) addresses from xpub/ypub/zpub."""
    try:
        from bip_utils import Bip44, Bip44Changes, Bip44Coins, Bip49, Bip49Coins, Bip84, Bip84Coins
    except Exception:
        log.warning("bip_utils not installed; cannot derive BTC addresses from extended pubkey")
        return []

    raw = (identifier or "").strip()
    if not raw:
        return []
    try:
        if raw.startswith("zpub"):
            ctx = Bip84.FromExtendedKey(raw, Bip84Coins.BITCOIN)
        elif raw.startswith("ypub"):
            ctx = Bip49.FromExtendedKey(raw, Bip49Coins.BITCOIN)
        else:
            ctx = Bip44.FromExtendedKey(raw, Bip44Coins.BITCOIN)
        chain = ctx.Change(Bip44Changes.CHAIN_EXT)
    except Exception:
        log.exception("failed to initialize BTC derivation from extended pubkey")
        return []

    out: list[str] = []
    for i in range(max_scan):
        try:
            out.append(chain.AddressIndex(i).PublicKey().ToAddress())
        except Exception:
            break
    return out


def _sum_derived_btc_balance_via_address_api(
    addresses: list[str],
    *,
    base_url: str,
    timeout: float,
    client: httpx.Client | None = None,
    gap_limit: int = 20,
) -> int:
    """Scan derived receive addresses with gap limit and return satoshis total."""
    if not addresses:
        return 0
    total_sats = 0
    consecutive_unused = 0

    def _fetch(url: str):
        if client is not None:
            return client.get(url)
        with httpx.Client(timeout=timeout) as cli:
            return cli.get(url)

    for addr in addresses:
        try:
            resp = _fetch(f"{base_url}/address/{addr}")
            resp.raise_for_status()
            payload = resp.json() or {}
        except Exception:
            # Ignore per-address errors and continue scanning.
            consecutive_unused += 1
            if consecutive_unused >= gap_limit:
                break
            continue

        chain_stats = payload.get("chain_stats") or {}
        mempool_stats = payload.get("mempool_stats") or {}
        funded = _safe_int(chain_stats, "funded_txo_sum") + _safe_int(mempool_stats, "funded_txo_sum")
        spent = _safe_int(chain_stats, "spent_txo_sum") + _safe_int(mempool_stats, "spent_txo_sum")
        satoshis = max(0, funded - spent)

        chain_txs = _safe_int(chain_stats, "tx_count")
        mempool_txs = _safe_int(mempool_stats, "tx_count")
        is_used = satoshis > 0 or (chain_txs + mempool_txs) > 0
        if is_used:
            consecutive_unused = 0
            total_sats += satoshis
        else:
            consecutive_unused += 1
            if consecutive_unused >= gap_limit:
                break
    return total_sats


def fetch_wallet_balances(
    address: str,
    *,
    timeout: float = 12.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch BTC balance for a Bitcoin address or extended public key.

    Returns a list with one row like {"symbol": "BTC", "balance": 0.01} when
    the balance is positive, otherwise returns an empty list.
    """
    identifier = (address or "").strip()
    if not is_bitcoin_mainnet_identifier(identifier):
        log.warning("invalid bitcoin wallet identifier: %s", address)
        return []

    base_url = (
        getattr(settings, "BTC_API_BASE", None)
        or "https://blockstream.info/api"
    ).rstrip("/")
    last_exc: Exception | None = None

    # Prefer deterministic local derivation for extended keys (xpub/ypub/zpub),
    # then use provider xpub endpoints only as fallback.
    if is_bitcoin_extended_public_key(identifier):
        try:
            derived_addresses = _derive_btc_mainnet_receive_addresses(identifier, max_scan=120)
            satoshis = _sum_derived_btc_balance_via_address_api(
                derived_addresses,
                base_url=base_url,
                timeout=timeout,
                client=client,
                gap_limit=20,
            )
            if satoshis > 0:
                btc = satoshis / 100_000_000
                return [{"symbol": "BTC", "name": "Bitcoin", "balance": btc}]
        except Exception as exc:
            last_exc = exc

    urls: list[str] = []
    normalized_extended_key = ""
    if is_bitcoin_extended_public_key(identifier):
        # Try the original key first (some providers support zpub/ypub directly).
        urls.append(f"{base_url}/xpub/{identifier}")
        if identifier.startswith(("ypub", "zpub")):
            try:
                normalized_extended_key = _normalize_mainnet_extended_pubkey(identifier)
            except Exception:
                normalized_extended_key = ""
            if normalized_extended_key and normalized_extended_key != identifier:
                urls.append(f"{base_url}/xpub/{normalized_extended_key}")
    elif is_bitcoin_address(identifier):
        urls.append(f"{base_url}/address/{identifier}")
    else:
        log.warning("unsupported bitcoin wallet identifier: %s", identifier)
        return []

    data: dict[str, Any] | None = None
    for url in urls:
        try:
            if client is not None:
                resp = client.get(url)
            else:
                with httpx.Client(timeout=timeout) as cli:
                    resp = cli.get(url)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            last_exc = exc
            continue
    if data is None:
        if is_bitcoin_extended_public_key(identifier):
            # Blockstream public API doesn't reliably support xpub/ypub/zpub.
            # Try alternative providers with best-effort fallbacks.
            fallback_urls = [
                f"{_BLOCKCHAIR_API_BASE}/bitcoin/dashboards/xpub/{identifier}?limit=0,0",
                f"{_HASKOIN_API_BASE}/btc/xpub/{identifier}/balance",
            ]
            if normalized_extended_key and normalized_extended_key != identifier:
                fallback_urls.append(
                    f"{_HASKOIN_API_BASE}/btc/xpub/{normalized_extended_key}/balance"
                )

            for fallback_url in fallback_urls:
                try:
                    if client is not None:
                        resp = client.get(fallback_url)
                    else:
                        with httpx.Client(timeout=timeout) as cli:
                            resp = cli.get(fallback_url)
                    resp.raise_for_status()
                    payload = resp.json() or {}

                    # Blockchair response.
                    if "blockchair.com" in fallback_url:
                        data_rows = payload.get("data") if isinstance(payload, dict) else None
                        if isinstance(data_rows, dict) and data_rows:
                            first_row = next(iter(data_rows.values()))
                            if isinstance(first_row, dict):
                                xpub_info = first_row.get("xpub") or {}
                                if isinstance(xpub_info, dict):
                                    satoshis = max(0, int(xpub_info.get("balance") or 0))
                                    if satoshis > 0:
                                        btc = satoshis / 100_000_000
                                        return [{"symbol": "BTC", "name": "Bitcoin", "balance": btc}]
                                    return []

                    # Haskoin-store response.
                    if "haskoin-store" in fallback_url and isinstance(payload, dict):
                        confirmed = int(payload.get("confirmed") or 0)
                        unconfirmed = int(payload.get("unconfirmed") or 0)
                        satoshis = max(0, confirmed + unconfirmed)
                        if satoshis > 0:
                            btc = satoshis / 100_000_000
                            return [{"symbol": "BTC", "name": "Bitcoin", "balance": btc}]
                        return []
                except Exception as exc:
                    last_exc = exc
                    continue
        if last_exc is not None:
            log.exception("failed to fetch BTC balance for wallet=%s", identifier, exc_info=last_exc)
        else:
            log.warning("failed to fetch BTC balance for wallet=%s", identifier)
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
