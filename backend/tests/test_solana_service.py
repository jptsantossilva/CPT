from types import SimpleNamespace

from backend.app.services import solana


def test_fetch_wallet_balances_parses_rpc_balance():
    class _Client:
        def post(self, _url, json=None):
            method = (json or {}).get("method")
            if method == "getBalance":
                payload = {"result": {"value": 2_500_000_000}}
            elif method == "getTokenAccountsByOwner":
                payload = {"result": {"value": []}}
            else:
                raise AssertionError(f"unexpected rpc method: {method}")
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    out = solana.fetch_wallet_balances(
        "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5",
        client=_Client(),
    )
    assert out == [{"symbol": "SOL", "name": "Solana", "balance": 2.5}]


def test_fetch_wallet_balances_returns_empty_for_invalid_address():
    out = solana.fetch_wallet_balances("not-a-solana-address")
    assert out == []


def test_fetch_wallet_balances_uses_fallback_endpoint(monkeypatch):
    monkeypatch.setenv("SOLANA_RPC_FALLBACK_URL", "https://api.mainnet.solana.com")

    class _Client:
        def post(self, url, json=None):
            method = (json or {}).get("method")
            if "primary.invalid" in url:
                raise RuntimeError("primary failed")
            if method == "getBalance":
                payload = {"result": {"value": 1_000_000_000}}
            elif method == "getTokenAccountsByOwner":
                payload = {"result": {"value": []}}
            else:
                raise AssertionError(f"unexpected rpc method: {method}")
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    out = solana.fetch_wallet_balances(
        "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5",
        rpc_url="https://primary.invalid",
        client=_Client(),
    )
    assert out == [{"symbol": "SOL", "name": "Solana", "balance": 1.0}]


def test_fetch_wallet_balances_includes_spl_tokens(monkeypatch):
    usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    helium_mint = "hntyvp6yfm1hg25tn9wglqm12b8tqmcknkrdu1oxwux"
    monkeypatch.setattr(
        solana,
        "_load_token_registry",
        lambda timeout=12.0: {
            usdc_mint.lower(): {"symbol": "USDC", "name": "USD Coin"},
            helium_mint.lower(): {"symbol": "HNT", "name": "Helium"},
        },
    )

    class _Client:
        def post(self, _url, json=None):
            method = (json or {}).get("method")
            if method == "getBalance":
                payload = {"result": {"value": 3_000_000_000}}
            elif method == "getTokenAccountsByOwner":
                params = (json or {}).get("params") or []
                program = (((params[1] if len(params) > 1 else {}) or {}).get("programId") or "").strip()
                if program != "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
                    payload = {"result": {"value": []}}
                    return SimpleNamespace(
                        raise_for_status=lambda: None,
                        json=lambda: payload,
                    )
                payload = {
                    "result": {
                        "value": [
                            {
                                "account": {
                                    "data": {
                                        "parsed": {
                                            "info": {
                                                "mint": usdc_mint,
                                                "tokenAmount": {"amount": "2500000", "decimals": 6},
                                            }
                                        }
                                    }
                                }
                            },
                            {
                                "account": {
                                    "data": {
                                        "parsed": {
                                            "info": {
                                                "mint": helium_mint,
                                                "tokenAmount": {"amount": "150000000", "decimals": 8},
                                            }
                                        }
                                    }
                                }
                            },
                        ]
                    }
                }
            else:
                raise AssertionError(f"unexpected rpc method: {method}")
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: payload,
            )

    out = solana.fetch_wallet_balances(
        "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5",
        client=_Client(),
    )

    assert {"symbol": "SOL", "name": "Solana", "balance": 3.0} in out
    assert {"symbol": "USDC", "name": "USD Coin", "balance": 2.5} in out
    assert {"symbol": "HNT", "name": "Helium", "balance": 1.5} in out
