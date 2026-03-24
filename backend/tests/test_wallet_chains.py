from backend.app.wallet_chains import (
    encode_wallet_identifier,
    is_bitcoin_address,
    is_bitcoin_extended_public_key,
    is_bitcoin_testnet_identifier,
    is_solana_address,
    normalize_wallet_chain,
    parse_wallet_identifier,
)


def test_parse_wallet_identifier_defaults_to_ethereum():
    chain, address = parse_wallet_identifier("0xabc")
    assert chain == "ethereum"
    assert address == "0xabc"


def test_parse_wallet_identifier_reads_prefix():
    chain, address = parse_wallet_identifier("base:0xabc")
    assert chain == "base"
    assert address == "0xabc"


def test_encode_wallet_identifier_keeps_ethereum_plain():
    out = encode_wallet_identifier("0xabc", "ethereum")
    assert out == "0xabc"


def test_encode_wallet_identifier_prefixes_base():
    out = encode_wallet_identifier("0xabc", "base")
    assert out == "base:0xabc"


def test_normalize_wallet_chain_rejects_unknown():
    try:
        normalize_wallet_chain("avalanche")
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_parse_wallet_identifier_detects_bitcoin_address():
    chain, address = parse_wallet_identifier("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert chain == "bitcoin"
    assert address == "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"


def test_encode_wallet_identifier_prefixes_bitcoin():
    out = encode_wallet_identifier("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "bitcoin")
    assert out == "bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"


def test_is_bitcoin_address_matches_main_types():
    assert is_bitcoin_address("1BoatSLRHtKNngkdXEeobR76b53LETtpyT")
    assert is_bitcoin_address("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
    assert is_bitcoin_address("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert is_bitcoin_address("bc1p5cyxnuxmeuwuvkwfem96llyvf8l0k2e8q8h0q3")


def test_parse_wallet_identifier_detects_bitcoin_extended_pubkey():
    key = "xpub661MyMwAqRbcFtXgS5s4f95m3nM2Z5Db5GsyhQ2E31x4n4t4WRPc8E9vrFica8FWHZpizxgxYkWwaP42CikLzeGWihcYZgToYtL6vhfV3hY"
    chain, identifier = parse_wallet_identifier(key)
    assert chain == "bitcoin"
    assert identifier == key


def test_is_bitcoin_extended_public_key_accepts_mainnet_prefixes():
    assert is_bitcoin_extended_public_key(
        "xpub661MyMwAqRbcFtXgS5s4f95m3nM2Z5Db5GsyhQ2E31x4n4t4WRPc8E9vrFica8FWHZpizxgxYkWwaP42CikLzeGWihcYZgToYtL6vhfV3hY"
    )
    assert is_bitcoin_extended_public_key(
        "ypub6X9fR2uWQmJ2j8QvrazS4eaXEusG3qY5T2r8j6YfGLwRoTSesQxFDXL9uBebquGsyhQ2E31x4n4t4WRPc8E9vrFica8FWHZpizxgxYkWwaP"
    )
    assert is_bitcoin_extended_public_key(
        "zpub6qfp6hKySx7wM4rWuHwoMvVJE9idhraNangNh4tW7x1YgnSUZXoqBYwygJyGTdQtdgQXVc3k5ufADG7n2AFDzy83H8XTur2qxGn8pYicbex"
    )


def test_is_bitcoin_testnet_identifier_detects_testnet_prefixes():
    assert is_bitcoin_testnet_identifier("tb1qfm8j9w0t5leq8v5uquk39z8f5j53xv0vjhlst2")
    assert is_bitcoin_testnet_identifier("mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn")
    assert is_bitcoin_testnet_identifier("2N2JD6wb56AfK4tfmM6PwdVmoYk2dCKf4Br")
    assert is_bitcoin_testnet_identifier(
        "tpubD6NzVbkrYhZ4W5o6v7BqXc9E8a1YKm4WxQ6VykBLL8GMDJ9ZhuttS5Agw7P3cu6UytzszbmWzxubUANe1yoynZMh1CT3VkHxVkkpFmS6rWC"
    )


def test_parse_wallet_identifier_detects_solana_address():
    addr = "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5"
    chain, address = parse_wallet_identifier(addr)
    assert chain == "solana"
    assert address == addr


def test_encode_wallet_identifier_prefixes_solana():
    addr = "5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5"
    out = encode_wallet_identifier(addr, "solana")
    assert out == f"solana:{addr}"


def test_is_solana_address_positive():
    assert is_solana_address("5H6v5T95h4L43KJfFv4Qw8VwM6NfY4uqpN7EzWLKQfU5")
