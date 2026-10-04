"""Refresh tokens: 32 random bytes that stand for a row in `sessions`.

A refresh token carries no claims. Everything it means lives in its session row,
which is what lets signing out and changing the password end it on the spot.

Only the SHA-256 of the token is stored. The token itself goes out once, in a
cookie, and is never written down: a database dump must not contain live
sessions.

SHA-256 and not Argon2id, deliberately. Argon2id is slow on purpose because a
password is short and guessable; 32 random bytes are on no list worth
precomputing, so the cost would buy nothing and would be paid on every refresh.
No salt either, for the same reason and because the lookup is *by* the hash.
"""

from __future__ import annotations

import hashlib
import secrets

TOKEN_BYTES = 32


def new_refresh_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def refresh_token_digest(token: str) -> bytes:
    encoded = token.encode()
    digest = hashlib.sha256(encoded)

    return digest.digest()
