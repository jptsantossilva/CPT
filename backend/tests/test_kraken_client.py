import base64

import httpx

from backend.app.services.kraken_client import (
    KrakenClient,
    MonotonicNonce,
    build_signature,
    normalize_asset,
)


def test_kraken_signature_and_monotonic_nonce(monkeypatch):
    secret = base64.b64encode(b"secret").decode()
    assert (
        build_signature(secret, "/0/private/Balance", "123456", {"account_id": "abc"})
        == "2EcTWU2MjYRxVE58XcmJaWNUIsDoBTlyVGKryTLlEh7SyurEvD3C884wSSn37pMASInK96bIixo0UvvD7c9hQQ=="
    )
    monkeypatch.setattr("backend.app.services.kraken_client.time.time", lambda: 1.0)
    nonce = MonotonicNonce()
    assert [nonce(), nonce(), nonce()] == ["1000", "1001", "1002"]


def test_kraken_asset_aliases_and_reward_extensions():
    assert normalize_asset("XXBT") == "BTC"
    assert normalize_asset("XDG.S") == "DOGE"
    assert normalize_asset("ZEUR") == "EUR"
    assert normalize_asset("XETH.M") == "ETH"


def test_kraken_wallet_accounts_are_kept_separate(monkeypatch):
    client = KrakenClient(
        "key",
        base64.b64encode(b"secret").decode(),
        client=httpx.Client(),
    )
    monkeypatch.setattr(client, "_asset_aliases", lambda: {"XXBT": "XBT"})

    def private(method, data=None):
        if method == "ListWalletAccounts":
            return [
                {"id": "spot", "name": "Spot", "state": "active"},
                {"id": "vault", "name": "Vault", "state": "active"},
            ]
        return {"XXBT": "1"} if data["account_id"] == "spot" else {"ZEUR": "25"}

    monkeypatch.setattr(client, "_private", private)
    rows, warnings = client.get_balance_sources()
    assert warnings == []
    assert [(r["source_id"], r["asset"], r["free"]) for r in rows] == [
        ("spot", "BTC", 1.0),
        ("vault", "EUR", 25.0),
    ]


def test_kraken_retries_rate_limit_without_logging_credentials(caplog):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"error": [], "result": {}})

    secret = base64.b64encode(b"private-secret").decode()
    client = KrakenClient(
        "private-key",
        secret,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        nonce_fn=lambda: "123456",
        sleep_fn=lambda _seconds: None,
    )
    assert client._private("Balance") == {}
    assert calls["count"] == 2
    assert "private-key" not in caplog.text
    assert secret not in caplog.text
