import httpx
import pytest

from backend.app.services.okx_client import OKXClient, OKX_BASE_URLS, build_signature


def test_okx_signature_and_region_hosts():
    assert (
        build_signature(
            "secret",
            "2020-12-08T09:08:57.715Z",
            "GET",
            "/api/v5/account/balance",
        )
        == "5ktoTKif8DCJlIPb/3Kfd1A17bIRye6jpS9QBWj+9AU="
    )
    assert OKX_BASE_URLS == {
        "eea": "https://eea.okx.com",
        "global": "https://openapi.okx.com",
        "us": "https://us.okx.com",
    }


def test_okx_combines_funding_and_trading_per_source(monkeypatch):
    client = OKXClient("key", "secret", "pass", client=httpx.Client())
    monkeypatch.setattr(
        client,
        "get_funding",
        lambda sub=None: [{"ccy": "BTC", "bal": "1", "availBal": "0.8"}]
        if sub is None
        else [{"ccy": "BTC", "bal": "2", "availBal": "2"}],
    )
    monkeypatch.setattr(
        client,
        "get_trading",
        lambda sub=None: [{"details": [{"ccy": "BTC", "cashBal": "0.5", "availBal": "0.4"}]}],
    )
    monkeypatch.setattr(client, "get_subaccounts", lambda: [{"subAcct": "desk-a", "label": "Desk A"}])

    rows, warnings = client.get_balance_sources()

    assert warnings == []
    assert [(row["source_id"], row["free"], row["locked"]) for row in rows] == [
        ("main", pytest.approx(1.2), pytest.approx(0.3)),
        ("desk-a", pytest.approx(2.4), pytest.approx(0.1)),
    ]


def test_okx_ignores_trading_liabilities():
    rows = OKXClient._merge_source(
        [{"ccy": "EUR", "bal": "10", "availBal": "10"}],
        [{"details": [{"ccy": "EUR", "cashBal": "-3", "availBal": "0"}]}],
    )
    assert rows == [{"asset": "EUR", "free": 10.0, "locked": 0.0}]


def test_okx_retries_rate_limits_without_logging_credentials(caplog):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"code": "0", "data": []})

    client = OKXClient(
        "private-key",
        "private-secret",
        "private-passphrase",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _seconds: None,
    )
    assert client.get_funding() == []
    assert calls["count"] == 2
    assert "private-secret" not in caplog.text
    assert "private-passphrase" not in caplog.text
