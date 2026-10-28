import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

SECRET_KEY = bytes.fromhex(settings.APP_ENCRYPTION_KEY)
aesgcm = AESGCM(SECRET_KEY)

def encrypt_value(plain_text: str) -> dict:
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    return {
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "iv": base64.b64encode(nonce).decode("utf-8"),
    }

def decrypt_value(ciphertext_b64: str, iv_b64: str) -> str:
    ciphertext = base64.b64decode(ciphertext_b64.encode("utf-8"))
    nonce = base64.b64decode(iv_b64.encode("utf-8"))
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")