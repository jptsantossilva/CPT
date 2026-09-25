from types import SimpleNamespace

from backend.app.services import sync


def test_exchange_sources_are_not_aggregated_together(monkeypatch):
    account = SimpleNamespace(
        id=7,
        provider="okx",
        identifier="master",
        label="OKX",
        include_subaccounts=True,
        api_key_encrypted="key",
        api_secret_encrypted="secret",
        api_passphrase_encrypted="pass",
    )
    monkeypatch.setattr(
        sync.okx,
        "fetch_balance_sources_for_account",
        lambda *_args, **_kwargs: (
            [
                {"asset": "BTC", "free": 1, "locked": 0, "source_id": "main", "source_label": "Main", "source_kind": "main"},
                {"asset": "BTC", "free": 2, "locked": 0, "source_id": "desk", "source_label": "Desk", "source_kind": "subaccount"},
            ],
            [],
        ),
    )
    rows, warnings, succeeded, failed = sync._sync_exchange_accounts_with_rows([account])
    assert warnings == []
    assert (succeeded, failed) == (1, 0)
    assert len(rows) == 2
    assert {row["source_key"] for row in rows} == {
        "okx:7:main:main",
        "okx:7:subaccount:desk",
    }
    assert {row["source_label"] for row in rows} == {"OKX", "OKX / Desk"}


def test_aggregate_only_merges_same_account_source_and_asset():
    rows = sync._aggregate_holdings(
        [
            {"account_id": 1, "source_key": "a", "asset_key": "symbol:BTC", "qty": 1},
            {"account_id": 1, "source_key": "a", "asset_key": "symbol:BTC", "qty": 2},
            {"account_id": 1, "source_key": "b", "asset_key": "symbol:BTC", "qty": 4},
        ]
    )
    assert sorted(row["qty"] for row in rows) == [3.0, 4]
