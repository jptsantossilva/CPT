from backend.app.services import nfts


def test_extract_opensea_collection_name_supports_string_or_dict_collection():
    assert (
        nfts._extract_opensea_collection_name({"collection": "Fontana by Harvey Rayner | patterndotco"})
        == "Fontana by Harvey Rayner | patterndotco"
    )
    assert nfts._extract_opensea_collection_name({"collection": {"name": "Fontana"}}) == "Fontana"
    assert nfts._extract_opensea_collection_name({"name": "Fallback Name"}) == "Fallback Name"


def test_fetch_nfts_for_wallet_builds_valuations(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x1",
                "name": f"{chain}-nft",
                "contract": {"address": "0xabc", "name": "Cool"},
                "collection": {"name": "Cool"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xabc": 2.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")

    # default configured chains: ethereum only
    assert len(out) == 1
    rows = {row["chain"]: row for row in out}
    assert rows["ethereum"]["valuation_usd"] == 4400
    assert rows["ethereum"]["valuation_symbol"] == "ETH"


def test_fetch_nfts_prefers_token_level_collection_name(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x2",
                "name": "Trichro-matic #296",
                "contract": {
                    "address": "0xdef",
                    "name": "(Dis)connected by Tibout Shaik",
                    "openSea": {"collectionName": "(Dis)connected by Tibout Shaik"},
                },
                "collection": {"name": "Trichro-matic by MountVitruvius"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xdef": 1.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["name"] == "Trichro-matic #296"
    assert row["collection"] == "Trichro-matic by MountVitruvius"


def test_fetch_nfts_prefers_collection_slug_over_wrong_name(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x2",
                "name": "Trichro-matic #296",
                "contract": {
                    "address": "0x99a9b7c1116f9ceeb1652de04d5969cce509b069",
                    "name": "(Dis)connected by Tibout Shaik",
                },
                "collection": {
                    "name": "(Dis)connected by Tibout Shaik",
                    "slug": "trichro-matic-by-mountvitruvius",
                },
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0x99a9b7c1116f9ceeb1652de04d5969cce509b069": 1.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["collection"] == "trichro matic by mountvitruvius"


def test_fetch_nfts_prefers_token_name_prefix_when_collection_conflicts(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x2",
                "name": "Trichro-matic #296",
                "contract": {
                    "address": "0x99a9b7c1116f9ceeb1652de04d5969cce509b069",
                    "name": "(Dis)connected by Tibout Shaik",
                },
                "collection": {
                    "name": "(Dis)connected by Tibout Shaik",
                    "slug": "dis-connected-by-tibout-shaik",
                },
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0x99a9b7c1116f9ceeb1652de04d5969cce509b069": 1.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["collection"] == "Trichro-matic"


def test_fetch_nfts_prefers_opensea_floor_when_available(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_slugs_for_nfts",
        lambda chain, nft_keys, api_key: {},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x2",
                "name": "Trichro-matic #296",
                "contract": {"address": "0xdef", "name": "Trichro-matic"},
                "collection": {"name": "Trichro-matic", "slug": "trichro-matic-by-mountvitruvius"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xdef": 0.14},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_floor_prices_for_slugs",
        lambda chain, slugs, api_key: {"trichro-matic-by-mountvitruvius": 0.17},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_collection_names_for_slugs",
        lambda chain, slugs, api_key: {"trichro-matic-by-mountvitruvius": "Trichro-matic by MountVitruvius"},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["valuation_native"] == 0.17
    assert row["collection"] == "Trichro-matic by MountVitruvius"


def test_fetch_nfts_uses_opensea_slug_by_contract_token(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "1000531",
                "name": "Amplitudes of Canvas #531",
                "contract": {
                    "address": "0x00000007cc35dcab4a396249aefa295a8b6e16ba",
                    "name": "Wrong Contract Collection",
                },
                "collection": {
                    "name": "Wrong Collection Name",
                    "slug": "wrong-slug",
                },
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0x00000007cc35dcab4a396249aefa295a8b6e16ba": 0.9},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_slugs_for_nfts",
        lambda chain, nft_keys, api_key: {
            ("0x00000007cc35dcab4a396249aefa295a8b6e16ba", "1000531"): "amplitudes-of-canvas-by-harvey-rayner"
        },
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_floor_prices_for_slugs",
        lambda chain, slugs, api_key: {"amplitudes-of-canvas-by-harvey-rayner": 0.08999},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_collection_names_for_slugs",
        lambda chain, slugs, api_key: {"amplitudes-of-canvas-by-harvey-rayner": "Amplitudes of Canvas"},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["collection_slug"] == "amplitudes-of-canvas-by-harvey-rayner"
    assert row["collection"] == "Amplitudes of Canvas"
    assert row["valuation_native"] == 0.08999


def test_fetch_nfts_marks_api_spam_as_hidden(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x3",
                "name": "Airdrop Scam",
                "contract": {"address": "0xspam"},
                "collection": {"name": "unknown"},
                "spamInfo": {"isSpam": True},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xspam": 0.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["is_spam"] is True
    assert row["visibility"] == "hidden"


def test_fetch_nfts_marks_low_unknown_without_floor_or_sale_as_hidden(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "0x4",
                "name": "Mystery NFT",
                "contract": {"address": "0xjunk"},
                "collection": {"name": "unknown"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xjunk": 0.0},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["has_floor_or_last_sale"] is False
    assert row["valuation_usd"] == 0.0
    assert row["visibility"] == "hidden"


def test_fetch_nfts_skips_contract_floor_for_shared_contract(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "367000498",
                "name": "Fontana #498",
                "contract": {"address": "0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270"},
                "collection": {"name": "Fontana by Harvey Rayner", "slug": "fontana-by-harvey-rayner-patterndotco"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_slugs_for_nfts",
        lambda chain, nft_keys, api_key: {},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_floor_prices_for_slugs",
        lambda chain, slugs, api_key: {"fontana-by-harvey-rayner-patterndotco": 0.0},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270": 2.5},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["valuation_native"] == 0.0
    assert row["valuation_source"] == "none"
    assert row["valuation_confidence"] == "low"


def test_fetch_nfts_uses_last_sale_when_floor_unavailable(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "367000498",
                "name": "Fontana #498",
                "contract": {"address": "0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270"},
                "collection": {"name": "Fontana by Harvey Rayner", "slug": "fontana-by-harvey-rayner-patterndotco"},
                "lastSale": {"price": {"amount": "0.55"}},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_slugs_for_nfts",
        lambda chain, nft_keys, api_key: {},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_floor_prices_for_slugs",
        lambda chain, slugs, api_key: {"fontana-by-harvey-rayner-patterndotco": 0.0},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xa7d8d9ef8d8ce8992df33d8b8cf4aebabd5bd270": 2.5},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {
            "ETH": {"price_eur": 2000, "price_usd": 2200},
            "POL": {"price_eur": 0.1, "price_usd": 0.11},
        },
    )

    out = nfts.fetch_nfts_for_wallet("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa")
    row = next((r for r in out if r["chain"] == "ethereum"), None)
    assert row is not None
    assert row["valuation_native"] == 0.55
    assert row["valuation_source"] == "nft_last_sale"
    assert row["valuation_confidence"] == "medium"


def test_fetch_nfts_skips_opensea_when_disabled(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_enabled", lambda: False)
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "1",
                "name": "NFT #1",
                "contract": {"address": "0xabc"},
                "collection": {"slug": "some-collection"},
            }
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xabc": 1.2},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {"ETH": {"price_eur": 2000, "price_usd": 2200}},
    )

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("opensea function should not be called when disabled")

    monkeypatch.setattr(nfts, "_fetch_opensea_slugs_for_nfts", _unexpected)
    monkeypatch.setattr(nfts, "_fetch_opensea_floor_prices_for_slugs", _unexpected)
    monkeypatch.setattr(nfts, "_fetch_opensea_collection_names_for_slugs", _unexpected)

    out = nfts.fetch_nfts_for_wallet("0xabc")
    assert len(out) == 1
    assert out[0]["valuation_native"] == 1.2


def test_fetch_nfts_filters_suspicious_slugs_before_opensea_lookups(monkeypatch):
    monkeypatch.setattr(nfts, "_alchemy_api_key", lambda: "k")
    monkeypatch.setattr(nfts, "_opensea_enabled", lambda: True)
    monkeypatch.setattr(nfts, "_opensea_api_key", lambda: "osk")
    monkeypatch.setattr(nfts, "_suspicious_slug_patterns", lambda: ["airdrop"])
    monkeypatch.setattr(
        nfts,
        "_fetch_owned_nfts_for_chain",
        lambda address, chain, api_key: [
            {
                "tokenId": "1",
                "name": "Good NFT #1",
                "contract": {"address": "0xaaa"},
                "collection": {"slug": "good-collection"},
            },
            {
                "tokenId": "2",
                "name": "Bad NFT #2",
                "contract": {"address": "0xbbb"},
                "collection": {"slug": "airdrop-collection"},
            },
        ],
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_floor_prices_for_contracts",
        lambda chain, contracts, api_key: {"0xaaa": 0.0, "0xbbb": 0.0},
    )
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_slugs_for_nfts",
        lambda chain, nft_keys, api_key: {},
    )
    seen_slugs: list[str] = []

    def _capture_slugs(chain, slugs, api_key):
        seen_slugs.extend(slugs)
        return {"good-collection": 0.4}

    monkeypatch.setattr(nfts, "_fetch_opensea_floor_prices_for_slugs", _capture_slugs)
    monkeypatch.setattr(
        nfts,
        "_fetch_opensea_collection_names_for_slugs",
        lambda chain, slugs, api_key: {"good-collection": "Good Collection"},
    )
    monkeypatch.setattr(
        nfts.prices,
        "fetch_prices",
        lambda symbols: {"ETH": {"price_eur": 2000, "price_usd": 2200}},
    )

    out = nfts.fetch_nfts_for_wallet("0xabc")
    assert len(out) == 2
    assert "good-collection" in seen_slugs
    assert "airdrop-collection" not in seen_slugs


def test_extract_is_spam_by_text_heuristics(monkeypatch):
    monkeypatch.setattr(
        nfts,
        "_suspicious_slug_patterns",
        lambda: ["usdcaward", "yieldether", "pooledeth"],
    )
    row = {
        "name": "Visit yieldether.org to claim rewards",
        "collection": {"name": "visit usdcaward com claim award 2"},
        "contract": {"address": "0xabc"},
    }
    assert nfts._extract_is_spam(row) is True


def test_extract_is_spam_keeps_regular_collection_non_spam(monkeypatch):
    monkeypatch.setattr(nfts, "_suspicious_slug_patterns", lambda: ["airdrop", "voucher"])
    row = {
        "name": "Fontana #498",
        "collection": {"name": "Fontana by Harvey Rayner | patterndotco"},
        "contract": {"address": "0xabc"},
    }
    assert nfts._extract_is_spam(row) is False
