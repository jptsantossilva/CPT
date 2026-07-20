import json

import httpx

from backend.app.services import eth


def test_fetch_wallet_balances_returns_eth_from_rpc():
    wallet = "0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"
    one_eth_wei_hex = hex(10**18)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        if "eth_chainId" in body:
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1"})
        if "eth_getBalance" in body:
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": one_eth_wei_hex})
        raise AssertionError(f"unexpected request: {body}")

    cli = httpx.Client(transport=httpx.MockTransport(handler))
    rows = eth.fetch_wallet_balances(wallet, rpc_url="https://rpc.local", client=cli)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "ETH"
    assert rows[0]["balance"] == 1.0


def test_fetch_wallet_balances_invalid_address_returns_empty():
    rows = eth.fetch_wallet_balances("not-an-address", rpc_url="https://rpc.local")
    assert rows == []


def test_fetch_wallet_balances_polygon_native_symbol_is_pol():
    wallet = "0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"
    one_pol_wei_hex = hex(10**18)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        if "eth_chainId" in body:
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": "0x89"})
        if "eth_getBalance" in body:
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": one_pol_wei_hex})
        raise AssertionError(f"unexpected request: {body}")

    cli = httpx.Client(transport=httpx.MockTransport(handler))
    rows = eth.fetch_wallet_balances(wallet, chain="polygon", rpc_url="https://rpc.local", client=cli)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "POL"
    assert rows[0]["balance"] == 1.0


def test_fetch_wallet_balances_returns_empty_on_chain_mismatch():
    wallet = "0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        if "eth_chainId" in body:
            # Ethereum chain id while requested chain is Polygon.
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1"})
        if "eth_getBalance" in body:
            return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": hex(10**18)})
        raise AssertionError(f"unexpected request: {body}")

    cli = httpx.Client(transport=httpx.MockTransport(handler))
    rows = eth.fetch_wallet_balances(wallet, chain="polygon", rpc_url="https://rpc.local", client=cli)
    assert rows == []


def test_fetch_wallet_balances_preserves_native_and_erc20_identity():
    wallet = "0x470BaB7c3E3e4FaDBA43AfAfc843149C6cBc3cFa"
    contract = "0x1111111111111111111111111111111111111111"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode("utf-8"))
        method = payload["method"]
        if method == "eth_chainId":
            result = "0x1"
        elif method == "eth_getBalance":
            result = hex(5 * 10**17)
        elif method == "alchemy_getTokenBalances":
            result = {"tokenBalances": [{"contractAddress": contract.upper(), "tokenBalance": hex(2 * 10**18)}]}
        elif method == "alchemy_getTokenMetadata":
            result = {"symbol": "ETH", "name": "Fake Ether", "decimals": 18}
        else:
            raise AssertionError(f"unexpected method: {method}")
        return httpx.Response(status_code=200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    cli = httpx.Client(transport=httpx.MockTransport(handler))
    rows = eth.fetch_wallet_balances(wallet, rpc_url="https://eth-mainnet.g.alchemy.com/v2/test", client=cli)

    assert rows[0] == {
        "symbol": "ETH",
        "name": "Ether",
        "contract": "native",
        "asset_kind": "native",
        "balance": 0.5,
    }
    assert rows[1] == {
        "symbol": "ETH",
        "name": "Fake Ether",
        "contract": contract,
        "asset_kind": "erc20",
        "balance": 2.0,
    }
