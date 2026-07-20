import json

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app import db
from backend.app.models import Account, Holding, Price, Snapshot
from backend.app.services import sync


def test_sync_excludes_hidden_erc20_spoof_from_prices_and_snapshot(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sync_identity.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(sync, "get_session", lambda: Session(engine))
    monkeypatch.setattr(db, "get_nft_blacklist_keys", lambda: set())
    monkeypatch.setattr(sync, "_wallet_rpc_warning", lambda: None)

    with Session(engine) as session:
        session.add(
            Account(
                provider="wallet",
                identifier="0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa",
                label="Wallet",
            )
        )
        session.commit()

    fake_contract = "0x1111111111111111111111111111111111111111"
    native = {
        "account_id": 1,
        "asset": "ETH",
        "qty": 0.5,
        "chain": "ethereum",
        "asset_key": "native:ethereum:ETH",
        "price_key": "symbol:ETH",
        "asset_kind": "native",
        "contract_address": None,
        "visibility": "visible",
        "risk_reason": None,
    }
    spoof = {
        "account_id": 1,
        "asset": "ETH",
        "qty": 2.25e58,
        "chain": "ethereum",
        "asset_key": f"erc20:ethereum:{fake_contract}",
        "price_key": f"erc20:ethereum:{fake_contract}",
        "asset_kind": "erc20",
        "contract_address": fake_contract,
        "visibility": "hidden",
        "risk_reason": "reserved_native_symbol",
    }

    monkeypatch.setattr(sync, "_sync_binance_accounts_with_rows", lambda _rows, on_progress=None: [])
    monkeypatch.setattr(sync, "_sync_wallet_accounts_with_rows", lambda _rows, on_progress=None: [native, spoof])
    monkeypatch.setattr(sync.nfts, "fetch_nfts_for_wallet", lambda _address: [])
    monkeypatch.setattr(
        sync.prices,
        "fetch_prices",
        lambda symbols: {"ETH": {"price_eur": 1800.0, "price_usd": 2000.0, "source": "test"}},
    )

    contract_calls = []

    def fake_contract_prices(rows):
        contract_calls.extend(rows)
        return {}

    monkeypatch.setattr(sync.prices, "fetch_evm_token_prices", fake_contract_prices)

    sync.sync_all("manual")

    assert contract_calls == []
    with Session(engine) as session:
        holdings = session.exec(select(Holding)).all()
        prices = session.exec(select(Price)).all()
        snapshots = session.exec(select(Snapshot)).all()

    assert len(holdings) == 2
    assert len(prices) == 1
    assert prices[0].price_key == "symbol:ETH"
    assert len(snapshots) == 1
    assert snapshots[0].total_eur == 900.0
    assert snapshots[0].total_usd == 1000.0
    meta = json.loads(snapshots[0].meta or "{}")
    assert meta["holdings_count"] == 1
    assert meta["hidden_holdings_count"] == 1
    assert meta["coins"] == [
        {
            "key": "ETH",
            "name": "ETH",
            "eur": 900.0,
            "usd": 1000.0,
            "qty": 0.5,
            "unit_eur": 1800.0,
            "unit_usd": 2000.0,
        }
    ]
