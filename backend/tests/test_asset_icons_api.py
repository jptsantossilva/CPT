from backend.app import main


def test_asset_icons_filters_unpriced_and_uses_cache_only_during_sync(monkeypatch):
    monkeypatch.setattr(
        main.db,
        "list_assets",
        lambda include_hidden=False: [
            {"asset_symbol": "BTC", "price_usd": 50000.0, "price_eur": 46000.0},
            {"asset_symbol": "SPAM", "price_usd": 0.0, "price_eur": 0.0},
        ],
    )
    monkeypatch.setattr(main.services.sync, "is_sync_running", lambda: True)
    calls = []

    def fake_fetch(symbols, *, allow_remote=True):
        calls.append((symbols, allow_remote))
        return {"BTC": "https://img.test/btc.png"}

    monkeypatch.setattr(main.services.prices, "fetch_icon_urls", fake_fetch)

    result = main.asset_icons("BTC,BTC,SPAM,UNKNOWN")

    assert result == {"BTC": "https://img.test/btc.png"}
    assert calls == [(["BTC"], False)]
