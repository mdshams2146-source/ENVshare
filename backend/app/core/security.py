import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from app.core.config import settings

password_hash = PasswordHash((BcryptHasher(),))

RESET_TOKEN_EXPIRE_MINUTES = 15

def get_reset_token_secret() -> str:
    """Returns dedicated reset token secret, strictly validating production entropy (AUTH-02)."""
    app_env = getattr(settings, "APP_ENV", "development").lower().strip()
    explicit = (os.getenv("RESET_TOKEN_SECRET") or getattr(settings, "RESET_TOKEN_SECRET", "")).strip()

    if app_env in ("production", "prod"):
        if not explicit:
            raise ValueError("In production, RESET_TOKEN_SECRET must be explicitly configured and cannot be empty.")
        if explicit == settings.JWT_SECRET:
            raise ValueError("In production, RESET_TOKEN_SECRET must be dedicated and distinct from JWT_SECRET.")
        if len(explicit.encode("utf-8")) < 32:
            raise ValueError("In production, RESET_TOKEN_SECRET must have at least 32 bytes of entropy.")
        return explicit

    # Clearly separated development-only fallback (never silently used in production)
    if explicit:
        return explicit
    return "dev-insecure-reset-token-secret-only-for-development-use-at-least-32-bytes"


def hash_token(token: str) -> str:
    """Computes SHA-256 hex digest of a token for secure database storage (AUTH-01)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.PyJWTError:
        return None

def create_password_reset_token(email: str) -> str:
    """Creates a short-lived signed JWT specifically for password reset."""
    secret = get_reset_token_secret()
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": email,
        "type": "reset",
        "exp": expire,
        "jti": str(uuid.uuid4())
    }
    return jwt.encode(to_encode, secret, algorithm=settings.JWT_ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[dict]:
    """Verifies the reset token signature and claims, returning payload if valid."""
    try:
        secret = get_reset_token_secret()
        payload = jwt.decode(
            token, secret, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "reset":
            return None
        return payload
    except Exception:
        return None
