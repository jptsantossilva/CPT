from backend.app.wallet_chains import (
    encode_wallet_identifier,
    is_bitcoin_address,
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
