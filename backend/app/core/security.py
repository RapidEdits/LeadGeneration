"""Password hashing, JWT issuance/verification, and credential encryption."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---- Passwords ----
def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---- JWT ----
def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ---- Credential encryption at rest (Fernet) ----
def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def encrypt_json(data: dict[str, Any]) -> str:
    return encrypt_secret(json.dumps(data, separators=(",", ":")))


def decrypt_json(ciphertext: str) -> dict[str, Any] | None:
    raw = decrypt_secret(ciphertext)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


# ---- Signed URL-safe tokens (HMAC over SECRET_KEY) ----
# Used for tamper-proof, optionally-expiring payloads embedded in public URLs:
# click-redirect targets (anti open-redirect) and OAuth `state`.
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_token(payload: dict[str, Any]) -> str:
    """Return `<b64(payload)>.<b64(sig)>`. Payload is signed, NOT encrypted."""
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def verify_token(token: str, *, max_age_seconds: int | None = None) -> dict[str, Any] | None:
    """Verify signature (and optional age via an `iat` claim). Returns payload or None."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64d(sig), expected):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (json.JSONDecodeError, ValueError):
        return None
    if max_age_seconds is not None:
        iat = payload.get("iat")
        if not isinstance(iat, (int, float)) or time.time() - iat > max_age_seconds:
            return None
    return payload
