from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt

from ..domain.constants import TokenClaim, TokenType
from .config import (
    ACCESS_TOKEN_TTL_MIN,
    JWT_ALGORITHM,
    JWT_SECRET,
    JWT_SECRET_MISSING_ERROR,
    REFRESH_TOKEN_TTL_DAYS,
)

if not JWT_SECRET:
    raise RuntimeError(JWT_SECRET_MISSING_ERROR)


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _encode_token(payload: dict) -> str:
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def issue_token_pair(*, user_email: str, roles: list[str], session_id: str) -> TokenPair:
    now = _now_utc()

    access_expires_at = now + timedelta(minutes=ACCESS_TOKEN_TTL_MIN)
    refresh_expires_at = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)

    access_payload = {
        TokenClaim.SUBJECT: user_email,
        TokenClaim.ROLES: roles,
        TokenClaim.ISSUED_AT: int(now.timestamp()),
        TokenClaim.EXPIRES_AT: int(access_expires_at.timestamp()),
        TokenClaim.JWT_ID: str(uuid4()),
        TokenClaim.SESSION_ID: session_id,
    }

    refresh_payload = {
        TokenClaim.SUBJECT: user_email,
        TokenClaim.ROLES: roles,
        TokenClaim.ISSUED_AT: int(now.timestamp()),
        TokenClaim.EXPIRES_AT: int(refresh_expires_at.timestamp()),
        TokenClaim.JWT_ID: str(uuid4()),
        TokenClaim.SESSION_ID: session_id,
        TokenClaim.TOKEN_TYPE: TokenType.REFRESH,
    }

    return TokenPair(
        access_token=_encode_token(access_payload),
        refresh_token=_encode_token(refresh_payload),
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )


__all__ = [
    "JWTError",
    "TokenPair",
    "decode_token",
    "generate_opaque_token",
    "hash_token",
    "issue_token_pair",
]
