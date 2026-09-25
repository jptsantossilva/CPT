from sqlalchemy import inspect, text
from sqlmodel import create_engine

from backend.app import db


def test_exchange_and_source_columns_are_added_to_legacy_tables(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy_exchange.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE account (id INTEGER PRIMARY KEY, provider VARCHAR NOT NULL, "
                "identifier VARCHAR NOT NULL, is_exchange BOOLEAN NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE holding (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, "
                "asset_symbol VARCHAR NOT NULL, quantity FLOAT NOT NULL)"
            )
        )
    monkeypatch.setattr(db, "engine", engine)
    db._ensure_account_exchange_columns()
    db._ensure_holding_identity_columns()
    account_columns = {column["name"] for column in inspect(engine).get_columns("account")}
    holding_columns = {column["name"] for column in inspect(engine).get_columns("holding")}
    assert {"api_passphrase_encrypted", "provider_region", "include_subaccounts"} <= account_columns
    assert {"source_key", "source_label", "source_kind"} <= holding_columns
