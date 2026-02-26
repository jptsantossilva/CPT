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


def test_sync_binance_accounts_disables_subaccount_merge_when_multiple(monkeypatch):
    rows = [
        SimpleNamespace(id=1, provider="binance"),
        SimpleNamespace(id=2, provider="binance"),
    ]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))

    flags: list[bool] = []

    def fake_fetch(account, *, include_subaccounts=True):
        flags.append(include_subaccounts)
        return [{"asset": "USDC", "free": 1, "locked": 0}]

    monkeypatch.setattr(sync.binance, "fetch_balances_for_account", fake_fetch)

    holdings = sync._sync_binance_accounts()

    assert len(holdings) == 2
    assert flags == [False, False]


def test_sync_binance_accounts_keeps_subaccount_merge_when_single(monkeypatch):
    rows = [SimpleNamespace(id=1, provider="binance")]
    monkeypatch.setattr(sync, "get_session", lambda: _FakeSessionCtx(rows))

    flags: list[bool] = []

    def fake_fetch(account, *, include_subaccounts=True):
        flags.append(include_subaccounts)
        return [{"asset": "USDC", "free": 1, "locked": 0}]

    monkeypatch.setattr(sync.binance, "fetch_balances_for_account", fake_fetch)

    holdings = sync._sync_binance_accounts()

    assert len(holdings) == 1
    assert flags == [True]
