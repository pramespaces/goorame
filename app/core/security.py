import hashlib
import hmac
import os
from typing import Optional


def get_password_hash(password: str, salt: Optional[str] = None) -> str:
    """SHA256 + salt, format `salt$hash` (kompatibel dengan database lama)."""
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, expected_hash = hashed_password.split("$", 1)
        actual = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected_hash, actual)
    except Exception:
        return False
