"""OKX account integration."""

from ..crypto import decrypt_text
from .okx_client import OKXClient


def fetch_balance_sources_for_account(account, *, include_subaccounts: bool = True):
    if not account.api_key_encrypted or not account.api_secret_encrypted or not account.api_passphrase_encrypted:
        return [], []
    with OKXClient(
        decrypt_text(account.api_key_encrypted),
        decrypt_text(account.api_secret_encrypted),
        decrypt_text(account.api_passphrase_encrypted),
        region=account.provider_region or "eea",
    ) as client:
        return client.get_balance_sources(include_subaccounts=include_subaccounts)
