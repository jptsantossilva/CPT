import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api import exchange_accounts
from backend.app.models import Account


def test_exchange_crud_masks_credentials_and_keeps_provider(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'exchange_api.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(exchange_accounts, "get_session", lambda: Session(engine))
    monkeypatch.setattr(exchange_accounts, "encrypt_text", lambda value: f"enc:{value}")
    monkeypatch.setattr(exchange_accounts, "decrypt_text", lambda value: value.removeprefix("enc:"))

    created = exchange_accounts.create_account(
        exchange_accounts.CreateExchangeAccount(
            provider="OKX",
            identifier="master",
            label="Desk",
            api_key="abcdefghijk",
            api_secret="top-secret",
            api_passphrase="my-passphrase-value",
            region="EEA",
        )
    )
    assert created["provider"] == "okx"
    assert created["api_key_masked"] == "abcd****hijk"
    assert "top-secret" not in str(created)
    assert "my-passphrase-value" not in str(created)
    listed = exchange_accounts.list_accounts()
    assert listed == [created]
    with Session(engine) as session:
        original = session.get(Account, created["id"])
        original_secret = original.api_secret_encrypted
        original_passphrase = original.api_passphrase_encrypted

    updated = exchange_accounts.update_account(
        created["id"],
        exchange_accounts.UpdateExchangeAccount(
            label="New label",
            api_key="",
            api_secret="",
            api_passphrase="",
        ),
    )
    assert updated["label"] == "New label"
    with Session(engine) as session:
        saved = session.get(Account, created["id"])
        assert saved.api_secret_encrypted == original_secret
        assert saved.api_passphrase_encrypted == original_passphrase

    with pytest.raises(HTTPException) as exc:
        exchange_accounts.update_account(
            created["id"],
            exchange_accounts.UpdateExchangeAccount(provider="kraken"),
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        exchange_accounts.create_account(
            exchange_accounts.CreateExchangeAccount(
                provider="okx",
                identifier="master",
                api_key="key",
                api_secret="secret",
                api_passphrase="pass",
                region="eea",
            )
        )
    assert exc.value.status_code == 409


def test_provider_specific_validation():
    with pytest.raises(HTTPException):
        exchange_accounts._validated("okx", "id", "key", "secret", None, "eea")
    with pytest.raises(HTTPException):
        exchange_accounts._validated("kraken", "id", "key", "secret", "not-used", None)
    with pytest.raises(HTTPException):
        exchange_accounts._validated("okx", "id", "key", "secret", "pass", "mars")


def test_legacy_binance_include_subaccounts_depends_on_account_count(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy_binance.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(exchange_accounts, "get_session", lambda: Session(engine))
    with Session(engine) as session:
        session.add(Account(provider="binance", identifier="one", is_exchange=True))
        session.commit()
    assert exchange_accounts.list_accounts()[0]["include_subaccounts"] is True
    with Session(engine) as session:
        session.add(Account(provider="binance", identifier="two", is_exchange=True))
        session.commit()
    assert all(not row["include_subaccounts"] for row in exchange_accounts.list_accounts())
