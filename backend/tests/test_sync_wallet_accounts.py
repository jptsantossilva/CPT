from types import SimpleNamespace

from backend.app.services import sync


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


class _FakeSessionCtx:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return _FakeSession(self._rows)

    def __exit__(self, *_):
        return None


def test_sync_wallet_accounts_maps_symbol_and_balance(monkeypatch):
    rows = [
        SimpleNamespace(id=3, provider="wallet", identifier="0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"),
    ]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))
    def fake_fetch(address, chain="ethereum"):
        if chain == "ethereum":
            return [{"symbol": "ETH", "balance": 0.5}, {"symbol": "USDC", "balance": 40}]
        if chain == "base":
            return [{"symbol": "USDC", "balance": 2}]
        return []

    monkeypatch.setattr(sync.eth, "fetch_wallet_balances", fake_fetch)

    holdings = sync._sync_wallet_accounts()

    assert holdings == [
        {"account_id": 3, "asset": "ETH", "qty": 0.5, "chain": "ethereum"},
        {"account_id": 3, "asset": "USDC", "qty": 40.0, "chain": "ethereum"},
        {"account_id": 3, "asset": "USDC", "qty": 2.0, "chain": "base"},
    ]


def test_sync_wallet_accounts_queries_ethereum_and_base(monkeypatch):
    rows = [
        SimpleNamespace(id=7, provider="wallet", identifier="base:0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"),
    ]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))

    seen: list[tuple[str, str]] = []

    def fake_fetch(address, chain="ethereum"):
        seen.append((address, chain))
        return [{"symbol": "ETH", "balance": 1}]

    monkeypatch.setattr(sync.eth, "fetch_wallet_balances", fake_fetch)

    holdings = sync._sync_wallet_accounts()

    assert holdings == [
        {"account_id": 7, "asset": "ETH", "qty": 1.0, "chain": "ethereum"},
        {"account_id": 7, "asset": "ETH", "qty": 1.0, "chain": "base"},
        {"account_id": 7, "asset": "ETH", "qty": 1.0, "chain": "polygon"},
    ]
    assert seen == [
        ("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa", "ethereum"),
        ("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa", "base"),
        ("0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa", "polygon"),
    ]


def test_sync_wallet_accounts_bitcoin_wallet_uses_btc_service(monkeypatch):
    rows = [
        SimpleNamespace(
            id=11,
            provider="wallet",
            identifier="bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        ),
    ]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))

    calls = {"eth": 0, "btc": 0}

    def fake_eth_fetch(_address, chain="ethereum"):
        calls["eth"] += 1
        return [{"symbol": "ETH", "balance": 1}]

    def fake_btc_fetch(address):
        calls["btc"] += 1
        assert address == "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        return [{"symbol": "BTC", "balance": 0.25}]

    monkeypatch.setattr(sync.eth, "fetch_wallet_balances", fake_eth_fetch)
    monkeypatch.setattr(sync.btc, "fetch_wallet_balances", fake_btc_fetch)

    holdings = sync._sync_wallet_accounts()

    assert holdings == [{"account_id": 11, "asset": "BTC", "qty": 0.25, "chain": "bitcoin"}]
    assert calls["btc"] == 1
    assert calls["eth"] == 0


def test_apply_nft_blacklist_forces_hidden_visibility():
    rows = [
        {
            "chain": "ethereum",
            "contract": "0xabc",
            "token_id": "1",
            "visibility": "visible",
        },
        {
            "chain": "polygon",
            "contract": "0xdef",
            "token_id": "2",
            "visibility": "visible",
        },
    ]
    blacklist = {("ethereum", "0xabc", "1")}
    out = sync._apply_nft_blacklist(rows, blacklist)
    assert out[0]["visibility"] == "hidden"
    assert out[1]["visibility"] == "visible"


def test_sync_wallet_accounts_solana_wallet_uses_solana_service(monkeypatch):
    rows = [
        SimpleNamespace(
            id=12,
            provider="wallet",
            identifier="solana:5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5",
        ),
    ]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))

    calls = {"eth": 0, "btc": 0, "sol": 0}

    def fake_eth_fetch(_address, chain="ethereum"):
        calls["eth"] += 1
        return [{"symbol": "ETH", "balance": 1}]

    def fake_btc_fetch(_address):
        calls["btc"] += 1
        return [{"symbol": "BTC", "balance": 0.25}]

    def fake_sol_fetch(address):
        calls["sol"] += 1
        assert address == "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5"
        return [{"symbol": "SOL", "balance": 3.5}]

    monkeypatch.setattr(sync.eth, "fetch_wallet_balances", fake_eth_fetch)
    monkeypatch.setattr(sync.btc, "fetch_wallet_balances", fake_btc_fetch)
    monkeypatch.setattr(sync.solana, "fetch_wallet_balances", fake_sol_fetch)

    holdings = sync._sync_wallet_accounts()

    assert holdings == [{"account_id": 12, "asset": "SOL", "qty": 3.5, "chain": "solana"}]
    assert calls["sol"] == 1
    assert calls["eth"] == 0
    assert calls["btc"] == 0
