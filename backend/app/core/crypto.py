import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

def validate_and_get_key() -> bytes:
    """Validates the encryption key format and length, returning 32-byte key for AES-256."""
    key_str = getattr(settings, "APP_ENCRYPTION_KEY", "")
    if not key_str:
        raise ValueError("APP_ENCRYPTION_KEY is required and cannot be empty")
    try:
        key_bytes = bytes.fromhex(key_str)
    except (ValueError, TypeError) as e:
        raise ValueError("APP_ENCRYPTION_KEY must be a valid hexadecimal string") from e
    if len(key_bytes) != 32:
        raise ValueError(
            f"APP_ENCRYPTION_KEY must be exactly 32 bytes (64 hex characters) for AES-256; got {len(key_bytes)} bytes"
        )
    return key_bytes

SECRET_KEY = validate_and_get_key()
aesgcm = AESGCM(SECRET_KEY)

def encrypt_value(plain_text: str) -> dict:
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    return {
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "iv": base64.b64encode(nonce).decode("utf-8"),
    }

def decrypt_value(ciphertext_b64: str, iv_b64: str) -> str:
    if not ciphertext_b64 or not iv_b64:
        raise ValueError("Both ciphertext and IV are required for decryption")
    ciphertext = base64.b64decode(ciphertext_b64.encode("utf-8"))
    nonce = base64.b64decode(iv_b64.encode("utf-8"))
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")
