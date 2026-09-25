"""Read-only Kraken Spot REST client."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)


class KrakenAPIError(RuntimeError):
    pass


def build_signature(secret: str, path: str, nonce: str, data: dict[str, Any]) -> str:
    encoded = urlencode({"nonce": nonce, **data})
    digest = hashlib.sha256((nonce + encoded).encode()).digest()
    mac = hmac.new(base64.b64decode(secret), path.encode() + digest, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


class MonotonicNonce:
    def __init__(self) -> None:
        self._last = 0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            value = max(int(time.time() * 1000), self._last + 1)
            self._last = value
            return str(value)


_nonce = MonotonicNonce()
_ALIASES = {
    "XXBT": "BTC", "XBT": "BTC", "XDG": "DOGE", "XXDG": "DOGE",
    "XETH": "ETH", "ETH2": "ETH", "ZEUR": "EUR", "ZUSD": "USD",
    "ZGBP": "GBP", "ZJPY": "JPY", "ZCAD": "CAD", "ZAUD": "AUD",
}


def normalize_asset(code: str, aliases: dict[str, str] | None = None) -> str:
    value = str(code or "").strip().upper()
    for suffix in (".S", ".M", ".B", ".F"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    # Explicit portfolio aliases take precedence over Kraken altname values
    # (notably XXBT -> BTC rather than XBT).
    merged = {**(aliases or {}), **_ALIASES}
    if value in merged:
        return merged[value].upper()
    if len(value) == 4 and value[0] in {"X", "Z"}:
        candidate = value[1:]
        if candidate in {"EUR", "USD", "GBP", "JPY", "CAD", "AUD", "CHF"}:
            return candidate
    return value


class KrakenClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = "https://api.kraken.com",
        timeout: float = 10.0,
        max_retries: int = 3,
        nonce_fn: Callable[[], str] = _nonce,
        sleep_fn: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.nonce_fn = nonce_fn
        self.sleep_fn = sleep_fn
        self._external_client = client is not None
        self.client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if not self._external_client:
            self.client.close()

    def __enter__(self) -> "KrakenClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _private(self, method: str, data: dict[str, Any] | None = None) -> Any:
        path = f"/0/private/{method}"
        body = dict(data or {})
        for attempt in range(self.max_retries + 1):
            nonce = self.nonce_fn()
            encoded = urlencode({"nonce": nonce, **body})
            headers = {
                "API-Key": self.api_key,
                "API-Sign": build_signature(self.api_secret, path, nonce, body),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            response = self.client.post(f"{self.base_url}{path}", headers=headers, content=encoded)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < self.max_retries:
                wait = float(response.headers.get("Retry-After") or 2**attempt)
                log.warning("Kraken request retry method=%s status=%s attempt=%s", method, response.status_code, attempt + 1)
                self.sleep_fn(wait)
                continue
            if response.status_code >= 400:
                raise KrakenAPIError(f"Kraken API error ({response.status_code}) on {method}")
            payload = response.json()
            errors = payload.get("error") or []
            if errors:
                if any("Rate limit" in str(error) or "Throttled" in str(error) for error in errors) and attempt < self.max_retries:
                    self.sleep_fn(float(2**attempt))
                    continue
                raise KrakenAPIError(f"Kraken API error on {method}: {', '.join(map(str, errors))}")
            return payload.get("result")
        raise KrakenAPIError(f"Kraken retry limit reached on {method}")

    def _asset_aliases(self) -> dict[str, str]:
        try:
            response = self.client.get(f"{self.base_url}/0/public/Assets")
            response.raise_for_status()
            result = response.json().get("result") or {}
            return {
                str(code).upper(): str(data.get("altname") or code).upper()
                for code, data in result.items()
            }
        except Exception as exc:
            log.warning("failed to load Kraken asset aliases: %s", exc)
            return {}

    def get_balance_sources(self) -> tuple[list[dict], list[str]]:
        aliases = self._asset_aliases()
        warnings: list[str] = []
        try:
            raw_wallets = self._private("ListWalletAccounts")
            if isinstance(raw_wallets, dict):
                wallets = raw_wallets.get("wallets") or raw_wallets.get("accounts") or []
                if not wallets:
                    wallets = [
                        {"id": wallet_id, **wallet}
                        for wallet_id, wallet in raw_wallets.items()
                        if isinstance(wallet, dict)
                    ]
            else:
                wallets = raw_wallets or []
            wallets = [
                wallet
                for wallet in wallets
                if isinstance(wallet, dict)
                and str(wallet.get("state") or wallet.get("status") or "active").lower()
                == "active"
            ]
        except KrakenAPIError as exc:
            log.warning("Kraken wallet account listing unavailable: %s", exc)
            wallets = []
            warnings.append("Kraken wallet account list unavailable; used default balance")
        sources = wallets or [{"id": "main", "name": "Main account"}]
        out: list[dict] = []
        for wallet in sources:
            source_id = str(wallet.get("id") or wallet.get("account_id") or "main")
            label = str(wallet.get("name") or wallet.get("label") or source_id)
            try:
                result = self._private("Balance", {} if source_id == "main" else {"account_id": source_id}) or {}
            except KrakenAPIError as exc:
                log.warning("failed to fetch Kraken wallet account=%s: %s", source_id, exc)
                warnings.append(f"Kraken wallet account failed: {label}")
                continue
            for raw_asset, raw_value in result.items():
                try:
                    total = float(raw_value or 0)
                except (TypeError, ValueError):
                    continue
                if total <= 0:
                    continue
                out.append(
                    {
                        "asset": normalize_asset(raw_asset, aliases),
                        "free": total,
                        "locked": 0.0,
                        "source_id": source_id,
                        "source_label": label,
                        "source_kind": "main" if source_id == "main" else "subaccount",
                    }
                )
        return out, warnings
