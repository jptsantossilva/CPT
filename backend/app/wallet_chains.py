"""Helpers for wallet chain handling without schema migration."""

from __future__ import annotations

import re

SUPPORTED_WALLET_CHAINS = {"ethereum", "base", "polygon", "bitcoin", "solana"}
DEFAULT_WALLET_CHAIN = "ethereum"

_BTC_BASE58_RE = re.compile(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$")
_BTC_BECH32_SEGWIT_RE = re.compile(r"^bc1q[ac-hj-np-z02-9]{11,71}$")
_BTC_BECH32M_TAPROOT_RE = re.compile(r"^bc1p[ac-hj-np-z02-9]{11,71}$")
_BTC_MAINNET_XPUB_RE = re.compile(r"^(xpub|ypub|zpub)[A-HJ-NP-Za-km-z1-9]{20,}$")
_BTC_TESTNET_BASE58_RE = re.compile(r"^[mn2][a-km-zA-HJ-NP-Z1-9]{25,34}$")
_BTC_TESTNET_BECH32_RE = re.compile(r"^(tb1|bcrt1)[ac-hj-np-z02-9]{11,71}$")
_BTC_TESTNET_XPUB_RE = re.compile(r"^(tpub|upub|vpub)[A-HJ-NP-Za-km-z1-9]{20,}$")
_SOL_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def is_bitcoin_address(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    low = raw.lower()
    return bool(
        _BTC_BASE58_RE.match(raw)
        or _BTC_BECH32_SEGWIT_RE.match(low)
        or _BTC_BECH32M_TAPROOT_RE.match(low)
    )


def is_bitcoin_extended_public_key(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    return bool(_BTC_MAINNET_XPUB_RE.match(raw))


def is_bitcoin_testnet_identifier(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    low = raw.lower()
    return bool(
        _BTC_TESTNET_BASE58_RE.match(raw)
        or _BTC_TESTNET_BECH32_RE.match(low)
        or _BTC_TESTNET_XPUB_RE.match(raw)
    )


def is_bitcoin_mainnet_identifier(value: str | None) -> bool:
    return is_bitcoin_address(value) or is_bitcoin_extended_public_key(value)


def is_solana_address(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    return bool(_SOL_BASE58_RE.match(raw))


def normalize_wallet_chain(value: str | None) -> str:
    chain = (value or DEFAULT_WALLET_CHAIN).strip().lower()
    if chain not in SUPPORTED_WALLET_CHAINS:
        raise ValueError(f"unsupported wallet chain: {chain}")
    return chain


def parse_wallet_identifier(identifier: str | None) -> tuple[str, str]:
    raw = (identifier or "").strip()
    if not raw:
        return DEFAULT_WALLET_CHAIN, ""
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        chain = prefix.strip().lower()
        if chain in SUPPORTED_WALLET_CHAINS:
            return chain, rest.strip()
    if is_bitcoin_mainnet_identifier(raw):
        return "bitcoin", raw
    if is_solana_address(raw):
        return "solana", raw
    return DEFAULT_WALLET_CHAIN, raw


def encode_wallet_identifier(address: str, chain: str | None) -> str:
    wallet = (address or "").strip()
    normalized_chain = normalize_wallet_chain(chain)
    if normalized_chain == DEFAULT_WALLET_CHAIN:
        return wallet
    return f"{normalized_chain}:{wallet}"
