import httpx
import pytest

from backend.app.services.binance_client import (
    BinanceClient,
    build_signature,
    merge_balances,
    normalize_balances,
)


def test_build_signature_known_value():
    query = "timestamp=1670000000000&recvWindow=5000"
    secret = "mysecret"
    got = build_signature(secret, query)
    assert (
        got == "356eca093c5871fbcf7da948cb0023d7009566b2a240b54fe54ef5f60d2dd804"
    )


def test_normalize_and_merge_balances_from_main_and_subaccounts():
    main = {
        "balances": [
            {"asset": "BTC", "free": "0.10", "locked": "0.02"},
            {"asset": "USDT", "free": "50", "locked": "0"},
            {"asset": "ETH", "free": "0", "locked": "0"},
        ]
    }
    sub = {
        "balances": [
            {"asset": "BTC", "free": "0.05", "locked": "0.00"},
            {"asset": "BNB", "free": "2", "locked": "1"},
        ]
    }

    merged = merge_balances([normalize_balances(main), normalize_balances(sub)])

    assert merged[0] == {"asset": "BNB", "free": 2.0, "locked": 1.0}
    assert merged[1]["asset"] == "BTC"
    assert merged[1]["free"] == pytest.approx(0.15)
    assert merged[1]["locked"] == pytest.approx(0.02)
    assert merged[2] == {"asset": "USDT", "free": 50.0, "locked": 0.0}


def test_get_account_retries_on_429_with_backoff():
    calls = {"count": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                status_code=429,
                headers={"Retry-After": "1"},
                json={"code": -1003, "msg": "Too many requests"},
            )
        return httpx.Response(status_code=200, json={"balances": []})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cli = BinanceClient(
        api_key="k",
        api_secret="s",
        client=client,
        sleep_fn=lambda s: sleeps.append(s),
        min_request_interval=0.0,
    )

    data = cli.get_account()

    assert data == {"balances": []}
    assert calls["count"] == 2
    assert sleeps == [1.0]


def test_get_all_balances_merges_subaccounts():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v3/account" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "balances": [
                        {"asset": "BTC", "free": "0.10", "locked": "0.01"},
                        {"asset": "USDT", "free": "20", "locked": "0"},
                    ]
                },
            )
        if "/sapi/v1/sub-account/list" in url:
            return httpx.Response(
                status_code=200,
                json={"subAccounts": [{"email": "sub1@test.local"}]},
            )
        if "/sapi/v3/sub-account/assets" in url:
            return httpx.Response(
                status_code=200,
                json={"balances": [{"asset": "BTC", "free": "0.2", "locked": "0"}]},
            )
        raise AssertionError(f"unexpected URL: {url}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cli = BinanceClient(
        api_key="k",
        api_secret="s",
        client=client,
        sleep_fn=lambda _: None,
        min_request_interval=0.0,
    )

    out = cli.get_all_balances(include_subaccounts=True)

    assert out[0]["asset"] == "BTC"
    assert out[0]["free"] == pytest.approx(0.3)
    assert out[0]["locked"] == pytest.approx(0.01)
    assert out[1] == {"asset": "USDT", "free": 20.0, "locked": 0.0}
