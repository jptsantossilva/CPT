from backend.app.services import prices


def test_fetch_prices_basic_with_monkeypatched_sources(monkeypatch):
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {"btc": "bitcoin", "eth": "ethereum"})
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {
            "bitcoin": {"eur": 50000, "usd": 54000},
            "ethereum": {"eur": 3000, "usd": 3250},
        },
    )

    mp = prices.fetch_prices(["BTC", "ETH", "USDT"])

    assert mp["BTC"]["price_eur"] == 50000
    assert mp["BTC"]["price_usd"] == 54000
    assert mp["ETH"]["price_eur"] == 3000
    assert mp["USDT"]["price_eur"] == 0.0


def test_fetch_prices_uses_symbol_override_for_one(monkeypatch):
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {"one": "some-wrong-one-id"})
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {
            "harmony": {"eur": 0.02, "usd": 0.022},
        },
    )

    mp = prices.fetch_prices(["ONE"])

    assert mp["ONE"]["price_eur"] == 0.02
    assert mp["ONE"]["price_usd"] == 0.022


def test_fetch_prices_uses_symbol_override_for_xlm(monkeypatch):
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {"xlm": "some-wrong-xlm-id"})
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {
            "stellar": {"eur": 0.12, "usd": 0.15},
        },
    )

    mp = prices.fetch_prices(["XLM"])

    assert mp["XLM"]["price_eur"] == 0.12
    assert mp["XLM"]["price_usd"] == 0.15


def test_fetch_prices_uses_symbol_override_for_ton(monkeypatch):
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {"ton": "some-wrong-ton-id"})
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {
            "the-open-network": {"eur": 1.75, "usd": 1.90},
        },
    )

    mp = prices.fetch_prices(["TON"])

    assert mp["TON"]["price_eur"] == 1.75
    assert mp["TON"]["price_usd"] == 1.90


def test_fetch_prices_uses_symbol_override_for_btc(monkeypatch):
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {"btc": "some-wrong-btc-id"})
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {
            "bitcoin": {"eur": 50000, "usd": 55000},
        },
    )

    mp = prices.fetch_prices(["BTC"])

    assert mp["BTC"]["price_eur"] == 50000
    assert mp["BTC"]["price_usd"] == 55000


def test_fetch_icon_urls_uses_overrides_for_gun_and_gps(monkeypatch):
    prices._icon_cache.clear()
    monkeypatch.setattr(prices, "_load_coin_list", lambda reload=False: {})
    monkeypatch.setattr(
        prices,
        "_fetch_coin_markets",
        lambda ids: {
            "gunz": {"id": "gunz", "image": "https://img.test/gunz.png"},
            "goplus-security": {"id": "goplus-security", "image": "https://img.test/gps.png"},
        },
    )

    mp = prices.fetch_icon_urls(["GUN", "GPS"])

    assert mp["GUN"] == "https://img.test/gunz.png"
    assert mp["GPS"] == "https://img.test/gps.png"
