import httpx

from backend.app import db
from backend.app.services import prices


def test_fetch_prices_basic_with_monkeypatched_sources(monkeypatch):
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {})
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
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"ONE": "harmony"})
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
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"XLM": "stellar"})
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
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"TON": "the-open-network"})
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
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"BTC": "bitcoin"})
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


def test_fetch_prices_uses_symbol_override_for_eth(monkeypatch):
    assert db.DEFAULT_PRICE_SYMBOL_MAPPINGS["ETH"]["provider_id"] == "ethereum"
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"ETH": "ethereum"})
    monkeypatch.setattr(
        prices,
        "_load_coin_list",
        lambda reload=False: {"eth": "anubis-bridged-eth-anubis"},
    )
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {"ethereum": {"eur": 1800.0, "usd": 2000.0}},
    )

    result = prices.fetch_prices(["ETH"])

    assert result["ETH"]["price_usd"] == 2000.0


def test_fetch_icon_urls_uses_overrides_for_gun_and_gps(monkeypatch):
    prices._icon_cache.clear()
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"GUN": "gunz", "GPS": "goplus-security"})
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


def test_fetch_evm_token_prices_uses_chain_and_contract(monkeypatch):
    prices._contract_price_cache.clear()
    requested_ids = []
    monkeypatch.setattr(
        prices,
        "_load_contract_id_map",
        lambda reload=False: {
            "ethereum:0x1111111111111111111111111111111111111111": "usd-coin",
        },
    )

    def fake_fetch(ids):
        requested_ids.extend(ids)
        return {"usd-coin": {"eur": 0.91, "usd": 1.0}}

    monkeypatch.setattr(prices, "_fetch_simple_price", fake_fetch)
    out = prices.fetch_evm_token_prices(
        [
            {
                "chain": "ethereum",
                "contract_address": "0x1111111111111111111111111111111111111111",
                "price_key": "erc20:ethereum:0x1111111111111111111111111111111111111111",
                "asset": "USDC",
            },
            {
                "chain": "ethereum",
                "contract_address": "0x2222222222222222222222222222222222222222",
                "price_key": "erc20:ethereum:0x2222222222222222222222222222222222222222",
                "asset": "ETH",
            },
        ]
    )

    assert requested_ids == ["usd-coin"]
    assert out["erc20:ethereum:0x1111111111111111111111111111111111111111"]["price_usd"] == 1.0
    missing = out["erc20:ethereum:0x2222222222222222222222222222222222222222"]
    assert missing["price_usd"] == 0.0
    assert missing["source"] == "coingecko_contract_missing"


def test_load_contract_id_map_indexes_supported_platform_contracts(monkeypatch):
    prices._contract_id_cache.update({"ts": 0, "data": {}, "loaded": False})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("include_platform") == "true"
        return httpx.Response(
            status_code=200,
            json=[
                {
                    "id": "usd-coin",
                    "symbol": "usdc",
                    "platforms": {
                        "ethereum": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                        "base": "0x833589fCD6EDB6E08f4C7C32D4f71b54bDa02913",
                        "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    },
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(prices.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))

    mapping = prices._load_contract_id_map(reload=True)

    assert mapping == {
        "ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin",
        "base:0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "usd-coin",
    }


def test_fetch_evm_token_prices_leaves_provider_failures_unpriced(monkeypatch):
    prices._contract_price_cache.clear()
    monkeypatch.setattr(prices, "_load_contract_id_map", lambda reload=False: None)

    out = prices.fetch_evm_token_prices(
        [
            {
                "chain": "base",
                "contract_address": "0x3333333333333333333333333333333333333333",
                "price_key": "erc20:base:0x3333333333333333333333333333333333333333",
                "asset": "WETH",
            }
        ]
    )

    row = out["erc20:base:0x3333333333333333333333333333333333333333"]
    assert row["price_eur"] == 0.0
    assert row["price_usd"] == 0.0
    assert row["source"] == "coingecko_contract_error"


def test_fetch_prices_distinguishes_provider_failure_from_missing(monkeypatch):
    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_load_symbol_mappings", lambda reload=False: {"ETH": "ethereum"})
    monkeypatch.setattr(prices, "_fetch_simple_price", lambda ids: None)

    failed = prices.fetch_prices(["ETH"])
    assert failed["ETH"]["source"] == "coingecko_error"

    prices._price_cache.clear()
    monkeypatch.setattr(prices, "_fetch_simple_price", lambda ids: {})
    missing = prices.fetch_prices(["ETH"])
    assert missing["ETH"]["source"] == "coingecko_missing"


def test_known_usdc_contract_skips_dynamic_contract_map(monkeypatch):
    prices._contract_price_cache.clear()
    dynamic_calls = []
    monkeypatch.setattr(
        prices,
        "_load_contract_id_map",
        lambda reload=False: dynamic_calls.append(True) or {},
    )
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {"usd-coin": {"eur": 0.92, "usd": 1.0}},
    )

    price_key = "erc20:ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    result = prices.fetch_evm_token_prices(
        [{
            "chain": "ethereum",
            "contract_address": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "price_key": price_key,
            "asset": "USDC",
        }]
    )

    assert dynamic_calls == []
    assert result[price_key]["price_usd"] == 1.0


def test_unknown_contract_falls_back_to_dynamic_contract_map(monkeypatch):
    prices._contract_price_cache.clear()
    contract = "0x1111111111111111111111111111111111111111"
    monkeypatch.setattr(
        prices,
        "_load_contract_id_map",
        lambda reload=False: {f"ethereum:{contract}": "other-token"},
    )
    monkeypatch.setattr(
        prices,
        "_fetch_simple_price",
        lambda ids: {"other-token": {"eur": 2.0, "usd": 2.2}},
    )

    key = f"erc20:ethereum:{contract}"
    result = prices.fetch_evm_token_prices(
        [{"chain": "ethereum", "contract_address": contract, "price_key": key, "asset": "OTHER"}]
    )

    assert result[key]["price_usd"] == 2.2


def test_icon_fetch_batches_and_stops_after_provider_failure(monkeypatch):
    prices._icon_cache.clear()
    monkeypatch.setattr(prices, "_cooldown_remaining", lambda: 0.0)
    monkeypatch.setattr(prices, "_resolve_symbol_id", lambda symbol: (f"id-{symbol}", False))
    batches = []

    def fake_markets(ids):
        batches.append(list(ids))
        if len(batches) == 2:
            return None
        return {coin_id: {"id": coin_id, "image": f"https://img/{coin_id}.png"} for coin_id in ids}

    monkeypatch.setattr(prices, "_fetch_coin_markets", fake_markets)
    result = prices.fetch_icon_urls([f"S{i}" for i in range(205)])

    assert [len(batch) for batch in batches] == [100, 100]
    assert len(result) == 100


def test_icon_429_sets_shared_cooldown_without_retrying(monkeypatch):
    prices._rate_limit_until = 0.0
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "12"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        prices.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    assert prices._fetch_coin_markets(["bitcoin"]) is None
    assert len(calls) == 1
    assert prices._cooldown_remaining() > 11
    prices._rate_limit_until = 0.0


def test_price_429_retries_and_respects_shared_cooldown(monkeypatch):
    prices._rate_limit_until = 0.0
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200, json={"usd-coin": {"eur": 0.92, "usd": 1.0}}),
    ]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses.pop(0)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(prices, "_wait_for_rate_limit", lambda: None)
    monkeypatch.setattr(
        prices.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    result = prices._fetch_simple_price(["usd-coin"])

    assert result == {"usd-coin": {"eur": 0.92, "usd": 1.0}}
    assert len(calls) == 2
    assert prices._cooldown_remaining() > 2
    prices._rate_limit_until = 0.0
