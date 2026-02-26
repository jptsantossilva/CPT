from cryptography.fernet import Fernet, InvalidToken
from typing import Optional
from .config import settings

_KEY = settings.ENCRYPTION_KEY
_FERNET: Optional[Fernet] = Fernet(_KEY.encode()) if _KEY else None


def encrypt_text(plaintext: str) -> str:
    if not _FERNET:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    return _FERNET.encrypt(plaintext.encode()).decode()


def decrypt_text(token: str) -> str:
    if not _FERNET:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("failed to decrypt token")
