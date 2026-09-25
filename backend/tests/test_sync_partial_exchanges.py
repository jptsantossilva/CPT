from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.models import Account, Holding, Snapshot
from backend.app.services import sync


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_partial_exchange_sync_persists_success_but_skips_snapshot(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(Account(provider="okx", identifier="master", is_exchange=True))
        session.commit()
    monkeypatch.setattr(sync, "get_session", lambda: Session(engine))
    monkeypatch.setattr(
        sync,
        "_sync_exchange_accounts_with_rows",
        lambda *_args, **_kwargs: (
            [{
                "account_id": 1, "asset": "BTC", "qty": 1.0,
                "asset_key": "symbol:BTC", "price_key": "symbol:BTC",
                "source_key": "okx:1:main:main", "source_label": "OKX",
                "source_kind": "main", "visibility": "visible",
            }],
            ["OKX subaccount failed: desk"],
            1,
            0,
        ),
    )
    monkeypatch.setattr(sync.prices, "fetch_prices", lambda _symbols: {"BTC": {"price_eur": 10, "price_usd": 11, "source": "test"}})
    monkeypatch.setattr(sync.prices, "fetch_evm_token_prices", lambda _rows: {})
    sync.sync_all()
    with Session(engine) as session:
        assert len(session.exec(select(Holding)).all()) == 1
        assert session.exec(select(Snapshot)).all() == []
    assert "Historical snapshot skipped" in str(sync.get_sync_status()["warning"])


def test_total_exchange_failure_preserves_previous_rows(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        account = Account(provider="kraken", identifier="main", is_exchange=True)
        session.add(account)
        session.commit()
        session.refresh(account)
        session.add(Holding(account_id=account.id, asset_symbol="BTC", quantity=2))
        session.add(Snapshot(total_eur=20, total_usd=22))
        session.commit()
    monkeypatch.setattr(sync, "get_session", lambda: Session(engine))
    monkeypatch.setattr(
        sync,
        "_sync_exchange_accounts_with_rows",
        lambda *_args, **_kwargs: ([], ["KRAKEN main failed"], 0, 1),
    )
    sync.sync_all()
    with Session(engine) as session:
        assert session.exec(select(Holding)).one().quantity == 2
        assert session.exec(select(Snapshot)).one().total_eur == 20
    assert sync.get_sync_status()["status"] == "failed"
