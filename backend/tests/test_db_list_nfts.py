from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from backend.app import db
from backend.app.models import Account, NFTHolding, Price


def test_list_nfts_recomputes_valuations_from_latest_prices(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nfts_prices.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "get_session", lambda: Session(engine))

    now = datetime.utcnow()
    with Session(engine) as s:
        account = Account(provider="wallet", identifier="ethereum:0xabc", label="Rainbow Main")
        s.add(account)
        s.commit()
        s.refresh(account)

        s.add(
            NFTHolding(
                account_id=int(account.id),
                chain="ethereum",
                contract="0xcontract",
                token_id="123",
                name="Example NFT",
                collection="Example Collection",
                valuation_symbol="ETH",
                valuation_native=0.5,
                valuation_usd=9999.0,
                valuation_eur=9999.0,
            )
        )
        s.add(Price(asset_symbol="ETH", price_usd=2000.0, price_eur=1800.0, ts=now - timedelta(hours=1)))
        s.add(Price(asset_symbol="ETH", price_usd=3000.0, price_eur=2700.0, price_key="symbol:ETH", ts=now))
        # A contract-scoped price with the same symbol must never leak into
        # native-symbol NFT valuation.
        s.add(
            Price(
                asset_symbol="ETH",
                price_usd=999999.0,
                price_eur=999999.0,
                price_key="erc20:ethereum:0x1111111111111111111111111111111111111111",
                ts=now + timedelta(minutes=1),
            )
        )
        s.commit()

    rows = db.list_nfts()

    assert len(rows) == 1
    row = rows[0]
    assert row["account_display"] == "Rainbow Main"
    assert row["account_identifier"] == "0xabc"
    assert row["valuation_symbol"] == "ETH"
    assert row["valuation_native"] == 0.5
    assert row["valuation_eth"] == 0.5
    assert row["valuation_usd"] == 1500.0
    assert row["valuation_eur"] == 1350.0


def test_list_nfts_keeps_persisted_valuation_when_symbol_price_missing(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nfts_fallback.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "get_session", lambda: Session(engine))

    with Session(engine) as s:
        account = Account(provider="wallet", identifier="0xdef", label="Wallet")
        s.add(account)
        s.commit()
        s.refresh(account)

        s.add(
            NFTHolding(
                account_id=int(account.id),
                chain="base",
                contract="0xcontract",
                token_id="999",
                valuation_symbol="WETH",
                valuation_native=0.1,
                valuation_usd=321.0,
                valuation_eur=300.0,
            )
        )
        s.commit()

    rows = db.list_nfts()

    assert len(rows) == 1
    row = rows[0]
    assert row["valuation_symbol"] == "WETH"
    assert row["valuation_usd"] == 321.0
    assert row["valuation_eur"] == 300.0
    assert row["valuation_eth"] is None


def test_list_nfts_hides_hidden_rows_by_default(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nfts_visibility.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "get_session", lambda: Session(engine))

    with Session(engine) as s:
        account = Account(provider="wallet", identifier="0x123", label="Wallet")
        s.add(account)
        s.commit()
        s.refresh(account)
        s.add(
            NFTHolding(
                account_id=int(account.id),
                chain="ethereum",
                contract="0xvisible",
                token_id="1",
                valuation_symbol="ETH",
                valuation_native=0.1,
                valuation_usd=100.0,
                valuation_eur=90.0,
                visibility="visible",
            )
        )
        s.add(
            NFTHolding(
                account_id=int(account.id),
                chain="ethereum",
                contract="0xhidden",
                token_id="2",
                valuation_symbol="ETH",
                valuation_native=0.0,
                valuation_usd=0.0,
                valuation_eur=0.0,
                visibility="hidden",
            )
        )
        s.commit()

    visible_only = db.list_nfts()
    all_rows = db.list_nfts(include_hidden=True)

    assert len(visible_only) == 1
    assert visible_only[0]["contract"] == "0xvisible"
    assert len(all_rows) == 2
