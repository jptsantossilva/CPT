"""Binance service integration."""

from typing import List

from ..crypto import decrypt_text
from .binance_client import BinanceClient


def fetch_balances_with_keys(
    api_key: str | None,
    api_secret: str | None,
    *,
    include_subaccounts: bool = True,
) -> List[dict]:
    """Fetch balances from Binance API keys.

    When include_subaccounts=True, main + subaccounts are merged.
    """
    if not api_key or not api_secret:
        return []

    with BinanceClient(api_key=api_key, api_secret=api_secret) as cli:
        return cli.get_all_balances(include_subaccounts=include_subaccounts)


def fetch_balances_for_account(account, *, include_subaccounts: bool = True) -> List[dict]:
    """Decrypt account keys and fetch balances."""
    if not account.api_key_encrypted or not account.api_secret_encrypted:
        return []
    api_key = decrypt_text(account.api_key_encrypted)
    api_secret = decrypt_text(account.api_secret_encrypted)
    return fetch_balances_with_keys(
        api_key,
        api_secret,
        include_subaccounts=include_subaccounts,
    )
