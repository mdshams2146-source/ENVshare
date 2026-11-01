import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from app.core.config import settings

password_hash = PasswordHash((BcryptHasher(),))

RESET_TOKEN_SECRET = os.getenv("RESET_TOKEN_SECRET", settings.JWT_SECRET)
RESET_TOKEN_EXPIRE_MINUTES = 15


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
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": email, "type": "reset", "exp": expire}
    return jwt.encode(to_encode, RESET_TOKEN_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verifies the reset token and returns the email if valid."""
    try:
        payload = jwt.decode(
            token, RESET_TOKEN_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "reset":
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None