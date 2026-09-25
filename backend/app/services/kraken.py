"""Kraken Spot account integration."""

from ..crypto import decrypt_text
from .kraken_client import KrakenClient


def fetch_balance_sources_for_account(account, **_kwargs):
    if not account.api_key_encrypted or not account.api_secret_encrypted:
        return [], []
    with KrakenClient(
        decrypt_text(account.api_key_encrypted),
        decrypt_text(account.api_secret_encrypted),
    ) as client:
        return client.get_balance_sources()
