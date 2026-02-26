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
