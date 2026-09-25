"""Read-only OKX v5 client for funding and spot trading balances."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)

OKX_BASE_URLS = {
    "eea": "https://eea.okx.com",
    "global": "https://openapi.okx.com",
    "us": "https://us.okx.com",
}


class OKXAPIError(RuntimeError):
    pass


def build_signature(secret: str, timestamp: str, method: str, request_path: str, body: str = "") -> str:
    payload = f"{timestamp}{method.upper()}{request_path}{body}".encode()
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


class OKXClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        *,
        region: str = "eea",
        timeout: float = 10.0,
        max_retries: int = 3,
        sleep_fn: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        region = region.strip().lower()
        if region not in OKX_BASE_URLS:
            raise ValueError("unsupported OKX region")
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = OKX_BASE_URLS[region]
        self.max_retries = max_retries
        self.sleep_fn = sleep_fn
        self._external_client = client is not None
        self.client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if not self._external_client:
            self.client.close()

    def __enter__(self) -> "OKXClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        query = urlencode(params or {})
        request_path = f"{path}?{query}" if query else path
        for attempt in range(self.max_retries + 1):
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            headers = {
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": build_signature(
                    self.api_secret, timestamp, "GET", request_path
                ),
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            }
            response = self.client.get(f"{self.base_url}{request_path}", headers=headers)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else float(2**attempt)
                log.warning("OKX request retry path=%s status=%s attempt=%s", path, response.status_code, attempt + 1)
                self.sleep_fn(wait)
                continue
            if response.status_code >= 400:
                raise OKXAPIError(f"OKX API error ({response.status_code}) on {path}")
            payload = response.json()
            if str(payload.get("code", "0")) != "0":
                raise OKXAPIError(f"OKX API error on {path}: code={payload.get('code')} msg={payload.get('msg')}")
            return payload.get("data") or []
        raise OKXAPIError(f"OKX API retry limit reached on {path}")

    def get_funding(self, subaccount: str | None = None) -> list[dict]:
        if subaccount:
            return self._request("/api/v5/asset/subaccount/balances", {"subAcct": subaccount})
        return self._request("/api/v5/asset/balances")

    def get_trading(self, subaccount: str | None = None) -> list[dict]:
        if subaccount:
            return self._request("/api/v5/account/subaccount/balances", {"subAcct": subaccount})
        return self._request("/api/v5/account/balance")

    def get_subaccounts(self) -> list[dict]:
        out: list[dict] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["after"] = after
            chunk = self._request("/api/v5/users/subaccount/list", params)
            out.extend(chunk)
            if len(chunk) < 100:
                break
            after = str(chunk[-1].get("uid") or "")
            if not after:
                break
        return out

    @staticmethod
    def _merge_source(funding: list[dict], trading: list[dict]) -> list[dict]:
        totals: dict[str, float] = {}
        available: dict[str, float] = {}
        for item in funding:
            symbol = str(item.get("ccy") or "").strip().upper()
            if not symbol:
                continue
            total = float(item.get("bal") or 0)
            if total <= 0:
                continue
            free = float(item.get("availBal") or total)
            totals[symbol] = totals.get(symbol, 0.0) + total
            available[symbol] = available.get(symbol, 0.0) + min(max(free, 0.0), max(total, 0.0))
        for account in trading:
            for item in account.get("details") or []:
                symbol = str(item.get("ccy") or "").strip().upper()
                if not symbol:
                    continue
                total = float(item.get("cashBal") or 0)
                # Negative cash balances represent liabilities and are outside
                # this Spot/cash portfolio scope.
                if total <= 0:
                    continue
                free = float(item.get("availBal") or total)
                totals[symbol] = totals.get(symbol, 0.0) + total
                available[symbol] = available.get(symbol, 0.0) + min(max(free, 0.0), max(total, 0.0))
        return [
            {"asset": symbol, "free": available.get(symbol, 0.0), "locked": max(total - available.get(symbol, 0.0), 0.0)}
            for symbol, total in sorted(totals.items())
            if total > 0
        ]

    def get_balance_sources(self, include_subaccounts: bool = True) -> tuple[list[dict], list[str]]:
        out: list[dict] = []
        warnings: list[str] = []

        def append_source(source_id: str, label: str, kind: str, subaccount: str | None = None) -> None:
            funding = self.get_funding(subaccount)
            trading = self.get_trading(subaccount)
            for item in self._merge_source(funding, trading):
                out.append({**item, "source_id": source_id, "source_label": label, "source_kind": kind})

        append_source("main", "Main account", "main")
        if include_subaccounts:
            try:
                subaccounts = self.get_subaccounts()
            except OKXAPIError as exc:
                log.warning("failed to list OKX subaccounts: %s", exc)
                return out, ["OKX subaccount list failed"]
            for sub in subaccounts:
                name = str(sub.get("subAcct") or "").strip()
                if not name:
                    continue
                try:
                    append_source(name, str(sub.get("label") or name), "subaccount", name)
                except OKXAPIError as exc:
                    log.warning("failed to fetch OKX subaccount=%s: %s", name, exc)
                    warnings.append(f"OKX subaccount failed: {name}")
        return out, warnings
