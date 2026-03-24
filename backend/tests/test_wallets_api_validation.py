from fastapi import HTTPException

from backend.app.api.wallets import (
    _assert_valid_bitcoin_identifier,
    _ensure_wallet_not_duplicate,
    _normalize_encoded_wallet_identifier,
)


def test_assert_valid_bitcoin_identifier_accepts_mainnet_address():
    _assert_valid_bitcoin_identifier("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")


def test_assert_valid_bitcoin_identifier_accepts_mainnet_xpub():
    _assert_valid_bitcoin_identifier(
        "xpub661MyMwAqRbcFtXgS5s4f95m3nM2Z5Db5GsyhQ2E31x4n4t4WRPc8E9vrFica8FWHZpizxgxYkWwaP42CikLzeGWihcYZgToYtL6vhfV3hY"
    )


def test_assert_valid_bitcoin_identifier_rejects_testnet():
    try:
        _assert_valid_bitcoin_identifier("tb1qfm8j9w0t5leq8v5uquk39z8f5j53xv0vjhlst2")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.detail == "Testnet not supported"


def test_normalize_encoded_wallet_identifier_normalizes_eth_case():
    out = _normalize_encoded_wallet_identifier("0xAbCdEf1234")
    assert out == "0xabcdef1234"


def test_normalize_encoded_wallet_identifier_normalizes_bitcoin_bech32_case():
    out = _normalize_encoded_wallet_identifier("bitcoin:BC1QXY2KGDYGJRSQTZQ2N0YRF2493P83KKFJHX0WLH")
    assert out == "bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"


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


def test_ensure_wallet_not_duplicate_detects_existing_wallet_case_insensitive_eth():
    rows = [type("Row", (), {"id": 1, "identifier": "0xabcdef1234"})()]
    session = _FakeSession(rows)
    try:
        _ensure_wallet_not_duplicate(
            session,
            encoded_identifier="0xAbCdEf1234",
        )
        assert False, "expected duplicate exception"
    except HTTPException as exc:
        assert exc.detail == "wallet already exists"


def test_ensure_wallet_not_duplicate_allows_same_wallet_id_on_update():
    rows = [type("Row", (), {"id": 1, "identifier": "bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"})()]
    session = _FakeSession(rows)
    _ensure_wallet_not_duplicate(
        session,
        encoded_identifier="bitcoin:BC1QXY2KGDYGJRSQTZQ2N0YRF2493P83KKFJHX0WLH",
        exclude_wallet_id=1,
    )
