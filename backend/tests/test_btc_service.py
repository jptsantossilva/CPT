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
