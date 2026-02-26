from backend.app.services import binance


def test_fetch_balances_with_keys_passes_include_subaccounts(monkeypatch):
    calls: list[bool] = []

    class DummyClient:
        def __init__(self, api_key: str, api_secret: str):
            self.api_key = api_key
            self.api_secret = api_secret

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get_all_balances(self, include_subaccounts: bool = True):
            calls.append(include_subaccounts)
            return [{"asset": "USDC", "free": 1.0, "locked": 0.0}]

    monkeypatch.setattr(binance, "BinanceClient", DummyClient)

    out = binance.fetch_balances_with_keys(
        "k",
        "s",
        include_subaccounts=False,
    )

    assert out == [{"asset": "USDC", "free": 1.0, "locked": 0.0}]
    assert calls == [False]


def test_fetch_balances_for_account_decrypts_and_propagates_flag(monkeypatch):
    class DummyAccount:
        api_key_encrypted = "enc-k"
        api_secret_encrypted = "enc-s"

    monkeypatch.setattr(binance, "decrypt_text", lambda value: "k" if value == "enc-k" else "s")

    seen: dict[str, object] = {}

    def fake_fetch(api_key, api_secret, *, include_subaccounts=True):
        seen["api_key"] = api_key
        seen["api_secret"] = api_secret
        seen["include_subaccounts"] = include_subaccounts
        return []

    monkeypatch.setattr(binance, "fetch_balances_with_keys", fake_fetch)

    binance.fetch_balances_for_account(DummyAccount(), include_subaccounts=False)

    assert seen == {
        "api_key": "k",
        "api_secret": "s",
        "include_subaccounts": False,
    }
