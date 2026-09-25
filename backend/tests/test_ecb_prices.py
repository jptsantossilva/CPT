import pytest

from backend.app.services import prices


def test_fiat_prices_use_ecb_rates(monkeypatch):
    prices._price_cache.clear()
    monkeypatch.setattr(
        prices,
        "_load_ecb_rates",
        lambda _symbols: {"EUR": 1.0, "USD": 1.2, "GBP": 0.8},
    )
    result = prices.fetch_prices(["EUR", "USD", "GBP"])
    assert result["EUR"]["price_eur"] == 1.0
    assert result["EUR"]["price_usd"] == 1.2
    assert result["USD"]["price_eur"] == pytest.approx(1 / 1.2)
    assert result["USD"]["price_usd"] == 1.0
    assert result["GBP"]["price_eur"] == 1.25
    assert result["GBP"]["price_usd"] == pytest.approx(1.5)
    assert {entry["source"] for entry in result.values()} == {"ecb"}
