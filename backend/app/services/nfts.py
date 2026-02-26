"""NFT service using Alchemy NFT API for ETH/Base/Polygon."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable, List

import httpx

from ..config import settings
from ..wallet_chains import SUPPORTED_WALLET_CHAINS
from . import prices

log = logging.getLogger(__name__)

_NETWORK_BY_CHAIN = {
    "ethereum": "eth-mainnet",
    "base": "base-mainnet",
    "polygon": "polygon-mainnet",
}

_NATIVE_SYMBOL_BY_CHAIN = {
    "ethereum": "ETH",
    "base": "ETH",
    "polygon": "POL",
}

_OPENSEA_CHAIN_BY_CHAIN = {
    "ethereum": "ethereum",
    "base": "base",
    "polygon": "matic",
}

_API_KEY_RE = re.compile(r"/(?:v2|nft/v3)/([^/?#]+)")
_OPENSEA_COLLECTION_RE = re.compile(r"/collection/([^/?#]+)")
_DEFAULT_SHARED_CONTRACTS = {
    # Art Blocks shared contract (multiple collections under same contract).
    "0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270",
    # Art Blocks Engine shared contract family where contract-floor can overstate token floor.
    "0x00000007cc35dcab4a396249aefa295a8b6e16ba",
}


def _extract_api_key(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    # Accept direct API key or full Alchemy URL (v2 / nft/v3).
    if raw.startswith("http://") or raw.startswith("https://"):
        m = _API_KEY_RE.search(raw)
        if m:
            return m.group(1)
        return None
    return raw


def _alchemy_api_key() -> str | None:
    explicit = getattr(settings, "ALCHEMY_API_KEY", None) or os.getenv("ALCHEMY_API_KEY")
    extracted_explicit = _extract_api_key(explicit)
    if extracted_explicit:
        return extracted_explicit

    for env_name in ("ETH_RPC_URL", "BASE_RPC_URL", "POLYGON_RPC_URL"):
        raw = getattr(settings, env_name, None) or os.getenv(env_name)
        extracted = _extract_api_key(raw)
        if extracted:
            return extracted
    return None


def _opensea_api_key() -> str | None:
    raw = getattr(settings, "OPENSEA_API_KEY", None) or os.getenv("OPENSEA_API_KEY")
    value = (raw or "").strip()
    return value or None


def _as_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _opensea_enabled() -> bool:
    raw = os.getenv("NFT_OPENSEA_ENABLED")
    if raw is None:
        return bool(getattr(settings, "NFT_OPENSEA_ENABLED", True))
    return _as_bool(raw, default=True)


def _opensea_max_lookups() -> int:
    raw = os.getenv("NFT_OPENSEA_MAX_LOOKUPS")
    if raw is None:
        return max(0, int(getattr(settings, "NFT_OPENSEA_MAX_LOOKUPS", 30) or 30))
    try:
        return max(0, int(raw))
    except Exception:
        return 30


def _nft_chains() -> list[str]:
    raw = os.getenv("NFT_CHAINS")
    if raw is None:
        raw = str(getattr(settings, "NFT_CHAINS", "ethereum") or "ethereum")
    requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
    allowed = [chain for chain in requested if chain in _NETWORK_BY_CHAIN]
    if not allowed:
        return ["ethereum"]
    return list(dict.fromkeys(allowed))


def _suspicious_slug_patterns() -> list[str]:
    raw = os.getenv("NFT_SCAM_SLUG_PATTERNS")
    if raw is None:
        raw = str(getattr(settings, "NFT_SCAM_SLUG_PATTERNS", "") or "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _shared_contracts() -> set[str]:
    raw = os.getenv("NFT_SHARED_CONTRACTS", "")
    parsed = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return _DEFAULT_SHARED_CONTRACTS | parsed


def _is_shared_contract(contract: str | None) -> bool:
    return (contract or "").strip().lower() in _shared_contracts()


def _is_suspicious_slug(slug: str | None) -> bool:
    s = (slug or "").strip().lower()
    if not s:
        return False
    for pat in _suspicious_slug_patterns():
        if pat and pat in s:
            return True
    return False


def _ordered_unique_str(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _ordered_unique_pair(values: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(values))


def _to_int_token_id(token_id: str | None) -> str:
    raw = (token_id or "").strip()
    if raw.startswith("0x"):
        try:
            return str(int(raw, 16))
        except Exception:
            return raw
    return raw


def _extract_floor_native(row: dict[str, Any]) -> float:
    candidates = []
    open_sea = row.get("openSea") or row.get("opensea") or {}
    candidates.append(open_sea.get("floorPrice"))
    looks_rare = row.get("looksRare") or row.get("looksrare") or {}
    candidates.append(looks_rare.get("floorPrice"))
    candidates.append(row.get("floorPrice"))
    for c in candidates:
        try:
            v = float(c)
            if v > 0:
                return v
        except Exception:
            continue
    return 0.0


def _to_positive_float(value: Any) -> float:
    try:
        v = float(value)
        return v if v > 0 else 0.0
    except Exception:
        return 0.0


def _extract_last_sale_native(row: dict[str, Any]) -> float:
    candidates: list[Any] = [
        row.get("lastSalePrice"),
        row.get("last_sale_price"),
    ]
    last_sale = row.get("lastSale") or {}
    if isinstance(last_sale, dict):
        price = last_sale.get("price") or {}
        if isinstance(price, dict):
            candidates.extend(
                [
                    price.get("amount"),
                    price.get("value"),
                    price.get("total"),
                ]
            )
        candidates.extend(
            [
                last_sale.get("price"),
                last_sale.get("amount"),
                last_sale.get("totalPrice"),
                last_sale.get("value"),
            ]
        )

    open_sea = row.get("openSea") or row.get("opensea") or {}
    if isinstance(open_sea, dict):
        candidates.append(open_sea.get("lastSalePrice"))

    for c in candidates:
        v = _to_positive_float(c)
        if v > 0:
            return v
    return 0.0


def _extract_is_spam(row: dict[str, Any]) -> bool:
    direct_flags = [row.get("isSpam"), row.get("spam"), (row.get("spamInfo") or {}).get("isSpam")]
    for v in direct_flags:
        if isinstance(v, bool):
            if v:
                return True
        elif str(v).strip().lower() in {"1", "true", "yes"}:
            return True

    for node in (row.get("spamInfo") or {}, (row.get("contract") or {}).get("spamInfo") or {}):
        if not isinstance(node, dict):
            continue
        classifications = node.get("classifications") or node.get("spamClassifications") or []
        if isinstance(classifications, list) and len(classifications) > 0:
            return True

    # Heuristic detection for common scam/drop spam NFTs that often evade API spam flags.
    slug = (_extract_collection_slug(row) or "").lower()
    name = str(row.get("name") or "").lower()
    collection_name = str(_extract_collection_name(row) or "").lower()
    text = " ".join([slug, name, collection_name])

    for pat in _suspicious_slug_patterns():
        p = (pat or "").strip().lower()
        if p and p in text:
            return True

    has_claim = any(k in text for k in ("claim", "redeem", "airdrop", "voucher", "reward", "rewards"))
    has_visit = "visit " in text or text.startswith("visit")
    has_domain = any(k in text for k in (".com", ".net", ".org", ".io", "http://", "https://"))
    if has_claim and (has_visit or has_domain):
        return True

    # Frequent scam naming: "visit xxx to claim rewards"
    if "visit" in text and "claim" in text and ("reward" in text or "rewards" in text):
        return True

    return False


def _slug_to_label(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    text = raw.replace("-", " ").replace("_", " ").strip()
    return text or None


def _normalize_name(value: str | None) -> str:
    raw = (value or "").lower()
    return "".join(ch for ch in raw if ch.isalnum())


def _collection_from_token_name(token_name: str | None) -> str | None:
    raw = (token_name or "").strip()
    if not raw or "#" not in raw:
        return None
    left, _, right = raw.rpartition("#")
    if not left.strip() or not right.strip().isdigit():
        return None
    return left.strip()


def _extract_collection_slug(row: dict[str, Any]) -> str | None:
    collection = row.get("collection") or {}
    row_open_sea = row.get("openSea") or row.get("opensea") or {}
    contract = row.get("contract") or {}
    contract_open_sea = contract.get("openSea") or contract.get("opensea") or {}
    for value in (
        collection.get("slug"),
        row_open_sea.get("collectionSlug"),
        contract_open_sea.get("collectionSlug"),
    ):
        slug = (value or "").strip().lower()
        if slug:
            return slug
    return None


def _extract_opensea_nft_slug(data: dict[str, Any]) -> str | None:
    nft = data.get("nft") or {}
    candidates: list[str | None] = []
    collection_node = nft.get("collection")
    if isinstance(collection_node, str):
        candidates.append(collection_node)
    elif isinstance(collection_node, dict):
        candidates.append(collection_node.get("slug"))
        candidates.append(collection_node.get("collection"))
    collection_top = data.get("collection")
    if isinstance(collection_top, str):
        candidates.append(collection_top)
    elif isinstance(collection_top, dict):
        candidates.append(collection_top.get("slug"))
        candidates.append(collection_top.get("collection"))
    for value in candidates:
        slug = (value or "").strip().lower()
        if slug:
            return slug

    # Fallback: parse from opensea URL if present.
    for value in (nft.get("opensea_url"), data.get("opensea_url"), nft.get("openseaUrl"), data.get("openseaUrl")):
        url = (value or "").strip()
        if not url:
            continue
        m = _OPENSEA_COLLECTION_RE.search(url)
        if m:
            return m.group(1).lower()
    return None


def _extract_collection_name(row: dict[str, Any]) -> str:
    collection = row.get("collection") or {}
    row_open_sea = row.get("openSea") or row.get("opensea") or {}
    contract = row.get("contract") or {}
    contract_open_sea = contract.get("openSea") or contract.get("opensea") or {}

    # Prefer token-level canonical slug first; some providers return an incorrect collection name.
    name = (
        _slug_to_label(collection.get("slug"))
        or collection.get("name")
        or _slug_to_label(row_open_sea.get("collectionSlug"))
        or row_open_sea.get("collectionName")
        or _slug_to_label(contract_open_sea.get("collectionSlug"))
        or contract_open_sea.get("collectionName")
        or contract.get("name")
    )
    token_derived = _collection_from_token_name(row.get("name"))
    if name and token_derived:
        # Some APIs return a collection linked to the contract, not to the exact token.
        # If token name is "Collection #id" and API collection does not contain that collection prefix,
        # prefer token-derived value.
        token_norm = _normalize_name(token_derived)
        api_norm = _normalize_name(str(name))
        if token_norm and token_norm not in api_norm:
            return token_derived
    if name:
        return str(name)
    if token_derived:
        return token_derived
    return "unknown"


def _is_unknown_collection(name: str | None) -> bool:
    norm = _normalize_name(name)
    return norm in {
        "",
        "unknown",
        "unknowncollection",
        "unnamedcollection",
        "untitledcollection",
        "nocollection",
    }


def _fetch_owned_nfts_for_chain(
    address: str,
    chain: str,
    api_key: str,
    *,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    network = _NETWORK_BY_CHAIN[chain]
    base_url = f"https://{network}.g.alchemy.com/nft/v3/{api_key}"
    page_key: str | None = None
    with httpx.Client(timeout=timeout) as cli:
        while True:
            params: dict[str, Any] = {
                "owner": address,
                "withMetadata": "true",
                "pageSize": 100,
            }
            if page_key:
                params["pageKey"] = page_key
            resp = cli.get(f"{base_url}/getNFTsForOwner", params=params)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("ownedNfts") or []
            out.extend(rows)
            page_key = data.get("pageKey")
            if not page_key:
                break
    return out


def _fetch_floor_prices_for_contracts(
    chain: str,
    contracts: Iterable[str],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> dict[str, float]:
    network = _NETWORK_BY_CHAIN[chain]
    base_url = f"https://{network}.g.alchemy.com/nft/v3/{api_key}"
    out: dict[str, float] = {}
    unique = sorted({c.lower() for c in contracts if c})
    if not unique:
        return out
    with httpx.Client(timeout=timeout) as cli:
        for contract in unique:
            try:
                resp = cli.get(f"{base_url}/getFloorPrice", params={"contractAddress": contract})
                resp.raise_for_status()
                data = resp.json()
                out[contract] = _extract_floor_native(data)
            except Exception:
                out[contract] = 0.0
    return out


def _extract_opensea_floor(data: dict[str, Any]) -> float:
    # Support both legacy and v2 response shapes.
    candidates = []
    stats = data.get("stats") or {}
    total = data.get("total") or {}
    candidates.append(stats.get("floor_price"))
    candidates.append(total.get("floor_price"))
    candidates.append(data.get("floor_price"))
    for c in candidates:
        try:
            v = float(c)
            if v > 0:
                return v
        except Exception:
            continue
    return 0.0


def _fetch_opensea_floor_prices_for_slugs(
    chain: str,
    slugs: Iterable[str],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> dict[str, float]:
    out: dict[str, float] = {}
    unique = _ordered_unique_str((s or "").strip().lower() for s in slugs if (s or "").strip())
    max_lookups = _opensea_max_lookups()
    if max_lookups > 0 and len(unique) > max_lookups:
        log.info("limiting OpenSea floor lookups from %s to %s", len(unique), max_lookups)
        unique = unique[:max_lookups]
    if not unique:
        return out
    chain_param = _OPENSEA_CHAIN_BY_CHAIN.get(chain)
    with httpx.Client(timeout=timeout) as cli:
        for slug in unique:
            try:
                params = {"chain": chain_param} if chain_param else None
                resp = cli.get(
                    f"https://api.opensea.io/api/v2/collections/{slug}/stats",
                    params=params,
                    headers={"x-api-key": api_key},
                )
                resp.raise_for_status()
                out[slug] = _extract_opensea_floor(resp.json())
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code == 429:
                    log.warning(
                        "opensea stats lookup rate-limited for chain=%s slug=%s; pausing remaining lookups",
                        chain,
                        slug,
                    )
                    break
                log.warning(
                    "opensea stats lookup failed for chain=%s slug=%s status=%s",
                    chain,
                    slug,
                    code,
                )
                out[slug] = 0.0
            except Exception:
                log.warning(
                    "opensea stats lookup failed for chain=%s slug=%s",
                    chain,
                    slug,
                )
                out[slug] = 0.0
    return out


def _fetch_opensea_slugs_for_nfts(
    chain: str,
    nft_keys: Iterable[tuple[str, str]],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    chain_param = _OPENSEA_CHAIN_BY_CHAIN.get(chain)
    if not chain_param:
        return out

    unique = _ordered_unique_pair(
        ((c or "").strip().lower(), (t or "").strip()) for c, t in nft_keys if (c or "").strip() and (t or "").strip()
    )
    max_lookups = _opensea_max_lookups()
    if max_lookups > 0 and len(unique) > max_lookups:
        log.info("limiting OpenSea NFT lookups from %s to %s", len(unique), max_lookups)
        unique = unique[:max_lookups]
    if not unique:
        return out

    with httpx.Client(timeout=timeout) as cli:
        for contract, token_id in unique:
            try:
                resp = cli.get(
                    f"https://api.opensea.io/api/v2/chain/{chain_param}/contract/{contract}/nfts/{token_id}",
                    headers={"x-api-key": api_key},
                )
                resp.raise_for_status()
                slug = _extract_opensea_nft_slug(resp.json())
                if slug:
                    out[(contract, token_id)] = slug
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code == 429:
                    log.warning(
                        "opensea nft lookup rate-limited for chain=%s; pausing remaining lookups",
                        chain,
                    )
                    break
                log.warning(
                    "opensea nft lookup failed for chain=%s contract=%s token_id=%s status=%s",
                    chain,
                    contract,
                    token_id,
                    code,
                )
            except Exception:
                log.warning(
                    "opensea nft lookup failed for chain=%s contract=%s token_id=%s",
                    chain,
                    contract,
                    token_id,
                )
                continue
    return out


def _extract_opensea_collection_name(data: dict[str, Any]) -> str | None:
    # Support possible response shapes from OpenSea endpoints.
    collection_node = data.get("collection")
    collection_name = (
        collection_node.get("name")
        if isinstance(collection_node, dict)
        else collection_node
        if isinstance(collection_node, str)
        else None
    )
    candidates = [
        data.get("name"),
        collection_name,
    ]
    collections = data.get("collections") or []
    if collections and isinstance(collections, list):
        first = collections[0] or {}
        if isinstance(first, dict):
            candidates.append(first.get("name"))
    for value in candidates:
        name = (value or "").strip()
        if name:
            return name
    return None


def _fetch_opensea_collection_names_for_slugs(
    chain: str,
    slugs: Iterable[str],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> dict[str, str]:
    out: dict[str, str] = {}
    unique = _ordered_unique_str((s or "").strip().lower() for s in slugs if (s or "").strip())
    max_lookups = _opensea_max_lookups()
    if max_lookups > 0 and len(unique) > max_lookups:
        log.info("limiting OpenSea collection-name lookups from %s to %s", len(unique), max_lookups)
        unique = unique[:max_lookups]
    if not unique:
        return out
    chain_param = _OPENSEA_CHAIN_BY_CHAIN.get(chain)
    with httpx.Client(timeout=timeout) as cli:
        for slug in unique:
            try:
                params = {"chain": chain_param} if chain_param else None
                resp = cli.get(
                    f"https://api.opensea.io/api/v2/collections/{slug}",
                    params=params,
                    headers={"x-api-key": api_key},
                )
                resp.raise_for_status()
                name = _extract_opensea_collection_name(resp.json())
                if name:
                    out[slug] = name
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code == 429:
                    log.warning(
                        "opensea collection lookup rate-limited for chain=%s slug=%s; pausing remaining lookups",
                        chain,
                        slug,
                    )
                    break
                log.warning(
                    "opensea collection lookup failed for chain=%s slug=%s status=%s",
                    chain,
                    slug,
                    code,
                )
            except Exception:
                log.warning(
                    "opensea collection lookup failed for chain=%s slug=%s",
                    chain,
                    slug,
                )
                continue
    return out


def fetch_nfts_for_wallet(address: str) -> List[dict]:
    api_key = _alchemy_api_key()
    if not api_key:
        log.warning("ALCHEMY_API_KEY not found (or not derivable from RPC URLs); skipping NFT fetch")
        return []

    chains = [c for c in _nft_chains() if c in SUPPORTED_WALLET_CHAINS]
    nfts_by_chain: dict[str, list[dict[str, Any]]] = {}
    for chain in chains:
        try:
            nfts_by_chain[chain] = _fetch_owned_nfts_for_chain(address, chain, api_key)
        except Exception:
            log.exception("failed fetching NFTs for wallet=%s chain=%s", address, chain)
            nfts_by_chain[chain] = []

    floor_by_chain_contract: dict[str, dict[str, float]] = {}
    floor_by_chain_slug: dict[str, dict[str, float]] = {}
    collection_name_by_chain_slug: dict[str, dict[str, str]] = {}
    preferred_slug_by_chain_nft: dict[str, dict[tuple[str, str], str]] = {}
    os_key = _opensea_api_key() if _opensea_enabled() else None
    for chain, rows in nfts_by_chain.items():
        contracts = [(r.get("contract") or {}).get("address", "") for r in rows]
        floor_by_chain_contract[chain] = _fetch_floor_prices_for_contracts(chain, contracts, api_key)
        nft_keys = [
            (
                ((r.get("contract") or {}).get("address") or "").lower(),
                _to_int_token_id(r.get("tokenId")),
            )
            for r in rows
        ]
        if os_key:
            non_spam_rows = [r for r in rows if not _extract_is_spam(r)]
            non_spam_nft_keys = [
                (
                    ((r.get("contract") or {}).get("address") or "").lower(),
                    _to_int_token_id(r.get("tokenId")),
                )
                for r in non_spam_rows
            ]
            slug_by_nft = _fetch_opensea_slugs_for_nfts(chain, non_spam_nft_keys, os_key)
            preferred_slug_by_chain_nft[chain] = slug_by_nft
            slugs = []
            for r in non_spam_rows:
                contract = ((r.get("contract") or {}).get("address") or "").lower()
                token_id = _to_int_token_id(r.get("tokenId"))
                slug = slug_by_nft.get((contract, token_id)) or _extract_collection_slug(r) or ""
                if slug and not _is_suspicious_slug(slug):
                    slugs.append(slug)
            floor_by_chain_slug[chain] = _fetch_opensea_floor_prices_for_slugs(chain, slugs, os_key)
            collection_name_by_chain_slug[chain] = _fetch_opensea_collection_names_for_slugs(
                chain, slugs, os_key
            )
        else:
            preferred_slug_by_chain_nft[chain] = {}
            floor_by_chain_slug[chain] = {}
            collection_name_by_chain_slug[chain] = {}

    symbols = sorted({_NATIVE_SYMBOL_BY_CHAIN[c] for c in chains})
    px = prices.fetch_prices(symbols)

    out: list[dict] = []
    for chain, rows in nfts_by_chain.items():
        native_symbol = _NATIVE_SYMBOL_BY_CHAIN[chain]
        native_px = px.get(native_symbol, {"price_eur": 0.0, "price_usd": 0.0})
        native_eur = float(native_px.get("price_eur", 0.0) or 0.0)
        native_usd = float(native_px.get("price_usd", 0.0) or 0.0)
        floor_map = floor_by_chain_contract.get(chain, {})
        floor_by_slug = floor_by_chain_slug.get(chain, {})
        name_by_slug = collection_name_by_chain_slug.get(chain, {})
        slug_by_nft = preferred_slug_by_chain_nft.get(chain, {})

        for row in rows:
            contract = ((row.get("contract") or {}).get("address") or "").lower()
            token_id = _to_int_token_id(row.get("tokenId"))
            slug = slug_by_nft.get((contract, token_id)) or _extract_collection_slug(row)
            collection_name = name_by_slug.get(slug or "") or _extract_collection_name(row)
            name = row.get("name") or f"{collection_name} #{token_id or '?'}"
            last_sale_native = _extract_last_sale_native(row)
            floor_from_slug = float(floor_by_slug.get(slug or "", 0.0) or 0.0)
            floor_from_contract = float(floor_map.get(contract, 0.0) or 0.0)
            valuation_native = 0.0
            valuation_source = "none"
            valuation_confidence = "low"

            if floor_from_slug > 0:
                valuation_native = floor_from_slug
                valuation_source = "opensea_collection_floor"
                valuation_confidence = "high"
            elif last_sale_native > 0:
                valuation_native = last_sale_native
                valuation_source = "nft_last_sale"
                valuation_confidence = "medium"
            elif floor_from_contract > 0 and not _is_shared_contract(contract):
                valuation_native = floor_from_contract
                valuation_source = "alchemy_contract_floor"
                valuation_confidence = "low"
            elif _is_shared_contract(contract):
                log.info(
                    "skip contract floor fallback for shared contract chain=%s contract=%s token_id=%s",
                    chain,
                    contract,
                    token_id,
                )

            has_floor_or_last_sale = valuation_native > 0
            is_spam = _extract_is_spam(row)
            valuation_usd = valuation_native * native_usd
            valuation_eur = valuation_native * native_eur
            visibility = "visible"
            if is_spam:
                visibility = "hidden"
            elif (
                valuation_usd <= 1.0
                and _is_unknown_collection(collection_name)
                and not has_floor_or_last_sale
            ):
                visibility = "hidden"
            out.append(
                {
                    "chain": chain,
                    "contract": contract,
                    "collection_slug": slug,
                    "token_id": token_id,
                    "name": name,
                    "collection": collection_name,
                    "owner": address,
                    "valuation_native": valuation_native,
                    "valuation_source": valuation_source,
                    "valuation_confidence": valuation_confidence,
                    "valuation_usd": valuation_usd,
                    "valuation_eur": valuation_eur,
                    "valuation_symbol": native_symbol,
                    "is_spam": is_spam,
                    "has_floor_or_last_sale": has_floor_or_last_sale,
                    "visibility": visibility,
                }
            )
    return out
