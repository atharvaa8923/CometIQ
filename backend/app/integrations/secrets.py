"""Encrypt secrets stored in the database (Canvas access and refresh tokens) with Fernet (AES-128-CBC + HMAC-SHA256)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings


def _fernet() -> Fernet:
    s = get_settings()
    if s.ENV == "production" and len(s.SECRETS_KEY) < 32:
        raise RuntimeError("Set SECRETS_KEY (32+ random characters) to store integration tokens")
    material = s.SECRETS_KEY or f"dev-only:{s.JWT_SECRET}"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def encrypt(value: str | None) -> str | None:
    return _fernet().encrypt(value.encode()).decode() if value else None


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None   # key changed: the user reconnects
