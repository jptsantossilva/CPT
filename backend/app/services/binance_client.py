"""Binance REST client with signed requests, retries, and balance normalization."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)


class BinanceAPIError(RuntimeError):
    """Raised when Binance returns a non-retryable error."""


@dataclass
class Balance:
    """Normalized Binance balance entry."""

    asset: str
    free: float
    locked: float


def build_signature(secret: str, query_string: str) -> str:
    """Return Binance HMAC SHA256 signature for a query string."""
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()


def normalize_balances(payload: dict[str, Any]) -> list[Balance]:
    """Parse raw Binance payload into normalized balance entries."""
    balances = payload.get("balances") or payload.get("assets") or []
    out: list[Balance] = []
    for item in balances:
        asset = (item.get("asset") or "").strip().upper()
        if not asset:
            continue
        try:
            free = float(item.get("free", 0) or 0)
            locked = float(item.get("locked", 0) or 0)
        except (TypeError, ValueError):
            continue
        if free == 0 and locked == 0:
            continue
        out.append(Balance(asset=asset, free=free, locked=locked))
    return out


def merge_balances(balance_groups: list[list[Balance]]) -> list[dict[str, float | str]]:
    """Merge balances from main account + subaccounts by asset symbol."""
    merged: dict[str, Balance] = {}
    for group in balance_groups:
        for b in group:
            current = merged.get(b.asset)
            if current is None:
                merged[b.asset] = Balance(asset=b.asset, free=b.free, locked=b.locked)
                continue
            current.free += b.free
            current.locked += b.locked

    return [
        {"asset": asset, "free": bal.free, "locked": bal.locked}
        for asset, bal in sorted(merged.items())
    ]


class BinanceClient:
    """Small Binance client focused on account and subaccount balances."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = "https://api.binance.com",
        timeout: float = 10.0,
        max_retries: int = 3,
        recv_window: int = 5000,
        min_request_interval: float = 0.1,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.recv_window = recv_window
        self.min_request_interval = min_request_interval
        self.sleep_fn = sleep_fn
        self.time_fn = time_fn
        self._last_request_ts = 0.0
        self._external_client = client is not None
        self.client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close underlying HTTP client when internally managed."""
        if not self._external_client:
            self.client.close()

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _throttle(self) -> None:
        now = self.time_fn()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_request_interval:
            self.sleep_fn(self.min_request_interval - elapsed)
        self._last_request_ts = self.time_fn()

    def _signed_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_params: dict[str, Any] = dict(params or {})
        query_params["recvWindow"] = self.recv_window
        query_params["timestamp"] = int(time.time() * 1000)
        query = urlencode(query_params, doseq=True)
        signature = build_signature(self.api_secret, query)
        signed_query = f"{query}&signature={signature}"
        url = f"{self.base_url}{path}?{signed_query}"
        headers = {"X-MBX-APIKEY": self.api_key}

        attempt = 0
        while True:
            self._throttle()
            resp = self.client.request(method, url, headers=headers)

            if resp.status_code in (429, 418) and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After")
                base_wait = float(retry_after) if retry_after else 1.0
                wait_s = base_wait * (2**attempt)
                log.warning(
                    "binance rate-limit status=%s path=%s retry=%s wait=%.2fs",
                    resp.status_code,
                    path,
                    attempt + 1,
                    wait_s,
                )
                self.sleep_fn(wait_s)
                attempt += 1
                continue

            if resp.status_code >= 500 and attempt < self.max_retries:
                wait_s = float(2**attempt)
                log.warning(
                    "binance server error status=%s path=%s retry=%s wait=%.2fs",
                    resp.status_code,
                    path,
                    attempt + 1,
                    wait_s,
                )
                self.sleep_fn(wait_s)
                attempt += 1
                continue

            if resp.status_code >= 400:
                msg = f"Binance API error ({resp.status_code}) on {path}"
                try:
                    body = resp.json()
                    code = body.get("code")
                    detail = body.get("msg")
                    msg = f"{msg}: code={code} msg={detail}"
                except Exception:
                    pass
                raise BinanceAPIError(msg)

            return resp.json()

    def get_account(self) -> dict[str, Any]:
        """Fetch main account details and balances."""
        return self._signed_request("GET", "/api/v3/account")

    def get_subaccounts(self, limit: int = 200) -> list[dict[str, Any]]:
        """List subaccounts with pagination."""
        page = 1
        out: list[dict[str, Any]] = []
        while True:
            data = self._signed_request(
                "GET",
                "/sapi/v1/sub-account/list",
                params={"page": page, "limit": limit},
            )
            chunk = data.get("subAccounts") or []
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < limit:
                break
            page += 1
        return out

    def get_subaccount_assets(self, email: str) -> dict[str, Any]:
        """Fetch balances for a single subaccount by email."""
        return self._signed_request(
            "GET", "/sapi/v3/sub-account/assets", params={"email": email}
        )

    def get_all_balances(self, include_subaccounts: bool = True) -> list[dict[str, float | str]]:
        """Fetch and merge balances from main account and optional subaccounts."""
        groups = [normalize_balances(self.get_account())]

        if include_subaccounts:
            try:
                subaccounts = self.get_subaccounts()
            except BinanceAPIError as exc:
                log.warning("failed to list subaccounts, using main account only: %s", exc)
                subaccounts = []

            for sub in subaccounts:
                email = sub.get("email")
                if not email:
                    continue
                try:
                    data = self.get_subaccount_assets(email)
                except BinanceAPIError as exc:
                    log.warning("failed to fetch subaccount assets email=%s: %s", email, exc)
                    continue
                groups.append(normalize_balances(data))

        return merge_balances(groups)
