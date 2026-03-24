from types import SimpleNamespace

from backend.app.services import btc


def test_fetch_wallet_balances_parses_blockstream_payload():
    class _Client:
        def get(self, _url):
            payload = {
                "chain_stats": {"funded_txo_sum": 150_000_000, "spent_txo_sum": 50_000_000},
                "mempool_stats": {"funded_txo_sum": 20_000_000, "spent_txo_sum": 10_000_000},
            }
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    out = btc.fetch_wallet_balances(
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        client=_Client(),
    )
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 1.1}]


def test_fetch_wallet_balances_returns_empty_for_invalid_address():
    out = btc.fetch_wallet_balances("not-an-address")
    assert out == []


def test_fetch_wallet_balances_uses_xpub_endpoint_for_mainnet_extended_pubkey(monkeypatch):
    calls = []
    monkeypatch.setattr(btc, "_derive_btc_mainnet_receive_addresses", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(btc, "_sum_derived_btc_balance_via_address_api", lambda *_args, **_kwargs: 0)

    class _Client:
        def get(self, url):
            calls.append(url)
            payload = {
                "chain_stats": {"funded_txo_sum": 120_000_000, "spent_txo_sum": 20_000_000},
                "mempool_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0},
            }
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    out = btc.fetch_wallet_balances(
        "xpub661MyMwAqRbcFtXgS5s4f95m3nM2Z5Db5GsyhQ2E31x4n4t4WRPc8E9vrFica8FWHZpizxgxYkWwaP42CikLzeGWihcYZgToYtL6vhfV3hY",
        client=_Client(),
    )
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 1.0}]
    assert len(calls) == 1
    assert "/xpub/" in calls[0]


def test_fetch_wallet_balances_tries_zpub_first_then_xpub_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(btc, "_derive_btc_mainnet_receive_addresses", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(btc, "_sum_derived_btc_balance_via_address_api", lambda *_args, **_kwargs: 0)

    class _Client:
        def get(self, url):
            calls.append(url)
            if len(calls) == 1:
                return SimpleNamespace(
                    raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("404")),
                    json=lambda: {},
                )
            payload = {
                "chain_stats": {"funded_txo_sum": 90_000_000, "spent_txo_sum": 10_000_000},
                "mempool_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0},
            }
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    zpub = "zpub6r6sYagmSAxJjqQLkZPZsW3J8TRHdLsuC4W1wEEUfbsixkvGQwWmDYp3L1K52EnhSVZ8AHs4BpVobV8s5bwSVGynnCgDgZoCx9o9LMGtdmB"
    out = btc.fetch_wallet_balances(zpub, client=_Client())
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 0.8}]
    assert len(calls) == 2
    assert f"/xpub/{zpub}" in calls[0]


def test_fetch_wallet_balances_falls_back_to_blockchair_for_extended_keys(monkeypatch):
    calls = []
    monkeypatch.setattr(btc, "_derive_btc_mainnet_receive_addresses", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(btc, "_sum_derived_btc_balance_via_address_api", lambda *_args, **_kwargs: 0)

    class _Client:
        def get(self, url):
            calls.append(url)
            if "blockstream.info" in url:
                return SimpleNamespace(
                    raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("404")),
                    json=lambda: {},
                )
            payload = {
                "data": {
                    "zpub-test": {
                        "xpub": {
                            "balance": 123_456_789,
                        }
                    }
                }
            }
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    zpub = "zpub6r6sYagmSAxJjqQLkZPZsW3J8TRHdLsuC4W1wEEUfbsixkvGQwWmDYp3L1K52EnhSVZ8AHs4BpVobV8s5bwSVGynnCgDgZoCx9o9LMGtdmB"
    out = btc.fetch_wallet_balances(zpub, client=_Client())
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 1.23456789}]
    assert any("blockchair.com/bitcoin/dashboards/xpub" in u for u in calls)


def test_fetch_wallet_balances_falls_back_to_haskoin_when_blockchair_is_rate_limited(monkeypatch):
    calls = []
    monkeypatch.setattr(btc, "_derive_btc_mainnet_receive_addresses", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(btc, "_sum_derived_btc_balance_via_address_api", lambda *_args, **_kwargs: 0)

    class _Client:
        def get(self, url):
            calls.append(url)
            if "blockstream.info" in url:
                return SimpleNamespace(
                    raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("404")),
                    json=lambda: {},
                )
            if "blockchair.com" in url:
                return SimpleNamespace(
                    raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("430")),
                    json=lambda: {},
                )
            payload = {"confirmed": 50_000_000, "unconfirmed": 12_345_678}
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    zpub = "zpub6r6sYagmSAxJjqQLkZPZsW3J8TRHdLsuC4W1wEEUfbsixkvGQwWmDYp3L1K52EnhSVZ8AHs4BpVobV8s5bwSVGynnCgDgZoCx9o9LMGtdmB"
    out = btc.fetch_wallet_balances(zpub, client=_Client())
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 0.62345678}]
    assert any("blockchair.com/bitcoin/dashboards/xpub" in u for u in calls)
    assert any("haskoin-store/btc/xpub" in u for u in calls)


def test_fetch_wallet_balances_uses_derivation_fallback_when_xpub_providers_fail(monkeypatch):
    class _Client:
        def get(self, _url):
            return SimpleNamespace(
                raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("fail")),
                json=lambda: {},
            )

    monkeypatch.setattr(
        btc,
        "_derive_btc_mainnet_receive_addresses",
        lambda _identifier, max_scan=120: ["bc1qtest1", "bc1qtest2"],
    )
    monkeypatch.setattr(
        btc,
        "_sum_derived_btc_balance_via_address_api",
        lambda _addresses, **_kwargs: 10_000_000,
    )

    zpub = "zpub6r6sYagmSAxJjqQLkZPZsW3J8TRHdLsuC4W1wEEUfbsixkvGQwWmDYp3L1K52EnhSVZ8AHs4BpVobV8s5bwSVGynnCgDgZoCx9o9LMGtdmB"
    out = btc.fetch_wallet_balances(zpub, client=_Client())
    assert out == [{"symbol": "BTC", "name": "Bitcoin", "balance": 0.1}]
