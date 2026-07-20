from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from backend.app import db
from backend.app.models import Account, Holding, Price


def test_list_assets_matches_prices_by_identity_and_hides_suspicious(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'assets_identity.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "get_session", lambda: Session(engine))

    fake_eth_contract = "0x1111111111111111111111111111111111111111"
    foo_contract_a = "0x2222222222222222222222222222222222222222"
    foo_contract_b = "0x3333333333333333333333333333333333333333"

    with Session(engine) as session:
        account = Account(
            provider="wallet",
            identifier="0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa",
            label="Wallet",
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        account_id = int(account.id)

        session.add_all(
            [
                Holding(
                    account_id=account_id,
                    asset_symbol="ETH",
                    asset_name="ethereum",
                    quantity=0.5,
                    asset_key="native:ethereum:ETH",
                    price_key="symbol:ETH",
                    asset_kind="native",
                ),
                Holding(
                    account_id=account_id,
                    asset_symbol="ETH",
                    asset_name="ethereum",
                    quantity=2.25e58,
                    asset_key=f"erc20:ethereum:{fake_eth_contract}",
                    price_key=f"erc20:ethereum:{fake_eth_contract}",
                    asset_kind="erc20",
                    contract_address=fake_eth_contract,
                    visibility="hidden",
                    risk_reason="reserved_native_symbol",
                ),
                Holding(
                    account_id=account_id,
                    asset_symbol="FOO",
                    asset_name="ethereum",
                    quantity=2.0,
                    asset_key=f"erc20:ethereum:{foo_contract_a}",
                    price_key=f"erc20:ethereum:{foo_contract_a}",
                    asset_kind="erc20",
                    contract_address=foo_contract_a,
                ),
                Holding(
                    account_id=account_id,
                    asset_symbol="FOO",
                    asset_name="ethereum",
                    quantity=3.0,
                    asset_key=f"erc20:ethereum:{foo_contract_b}",
                    price_key=f"erc20:ethereum:{foo_contract_b}",
                    asset_kind="erc20",
                    contract_address=foo_contract_b,
                ),
                Price(asset_symbol="ETH", price_eur=1800.0, price_usd=2000.0, price_key="symbol:ETH"),
                Price(
                    asset_symbol="FOO",
                    price_eur=1.0,
                    price_usd=1.1,
                    price_key=f"erc20:ethereum:{foo_contract_a}",
                ),
                Price(
                    asset_symbol="FOO",
                    price_eur=4.0,
                    price_usd=4.4,
                    price_key=f"erc20:ethereum:{foo_contract_b}",
                ),
            ]
        )
        session.commit()

    visible = db.list_assets()
    all_rows = db.list_assets(include_hidden=True)

    assert len(visible) == 3
    native = next(row for row in visible if row["asset_kind"] == "native")
    assert native["value_eur"] == 900.0
    foo_rows = sorted((row for row in visible if row["asset_symbol"] == "FOO"), key=lambda row: row["price_eur"])
    assert [(row["price_eur"], row["value_eur"]) for row in foo_rows] == [(1.0, 2.0), (4.0, 12.0)]

    assert len(all_rows) == 4
    hidden = next(row for row in all_rows if row["visibility"] == "hidden")
    assert hidden["contract_address"] == fake_eth_contract
    assert hidden["risk_reason"] == "reserved_native_symbol"
    assert hidden["price_eur"] == 0.0
    assert hidden["price_usd"] == 0.0
    assert hidden["value_eur"] == 0.0
    assert hidden["value_usd"] == 0.0


def test_identity_column_migrations_upgrade_legacy_tables(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", echo=False)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE holding ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, asset_symbol VARCHAR NOT NULL, "
                "asset_name VARCHAR, quantity FLOAT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE price ("
                "id INTEGER PRIMARY KEY, asset_symbol VARCHAR NOT NULL, price_eur FLOAT NOT NULL, "
                "price_usd FLOAT, ts DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE snapshot ("
                "id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL, total_eur FLOAT NOT NULL, "
                "total_usd FLOAT, meta VARCHAR)"
            )
        )
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_holding_identity_columns()
    db._ensure_price_identity_columns()
    db._ensure_snapshot_validity_columns()

    inspector = inspect(engine)
    holding_columns = {column["name"] for column in inspector.get_columns("holding")}
    price_columns = {column["name"] for column in inspector.get_columns("price")}
    snapshot_columns = {column["name"] for column in inspector.get_columns("snapshot")}
    assert {
        "asset_key",
        "price_key",
        "asset_kind",
        "contract_address",
        "visibility",
        "risk_reason",
    }.issubset(holding_columns)
    assert "price_key" in price_columns
    assert {"is_valid", "invalid_reason", "invalidated_at"}.issubset(snapshot_columns)


def test_snapshot_migration_uses_postgresql_compatible_timestamp(monkeypatch):
    statements = []

    class _Inspector:
        def get_table_names(self):
            return ["snapshot"]

        def get_columns(self, _table):
            return [
                {"name": "id"},
                {"name": "timestamp"},
                {"name": "total_eur"},
                {"name": "total_usd"},
                {"name": "meta"},
            ]

    class _Connection:
        def execute(self, statement):
            statements.append(str(statement))

    class _Begin:
        def __enter__(self):
            return _Connection()

        def __exit__(self, *_args):
            return None

    class _Engine:
        def begin(self):
            return _Begin()

    monkeypatch.setattr(db, "engine", _Engine())
    monkeypatch.setattr(db, "inspect", lambda _engine: _Inspector())

    db._ensure_snapshot_validity_columns()

    assert statements == [
        "ALTER TABLE snapshot ADD COLUMN is_valid BOOLEAN DEFAULT TRUE",
        "ALTER TABLE snapshot ADD COLUMN invalid_reason VARCHAR",
        "ALTER TABLE snapshot ADD COLUMN invalidated_at TIMESTAMP",
    ]
