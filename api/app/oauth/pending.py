"""A sign-in that went to the provider and has not come back yet.

`state` ties the callback to the browser that started the flow — without it,
someone could finish their own sign-in in your browser and have you working in
their account. The PKCE `verifier` ties the code to us: a code intercepted on the
way back is useless without it.

Both travel in a cookie, as a JWT signed with JWT_SECRET and typed
`oauth_state`, so it cannot be edited, outlives nothing by more than ten
minutes, and can never be mistaken for an access token (nor one for it).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from jwt.types import Options

PENDING_LIFETIME = timedelta(minutes=10)
ALGORITHM = "HS256"
TOKEN_TYPE = "oauth_state"

# RFC 7636 asks for 43 to 128 characters; 64 random bytes come out as 86.
VERIFIER_BYTES = 64


@dataclass(frozen=True)
class PendingSignIn:
    provider: str
    state: str
    verifier: str


def new_pending_sign_in(provider: str) -> PendingSignIn:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(VERIFIER_BYTES)

    return PendingSignIn(provider=provider, state=state, verifier=verifier)


def code_challenge(verifier: str) -> str:
    """S256: the base64url of the verifier's SHA-256, without padding."""
    digest = hashlib.sha256(verifier.encode()).digest()
    encoded = base64.urlsafe_b64encode(digest)

    return encoded.decode().rstrip("=")


def seal_pending(pending: PendingSignIn, secret: str, now: datetime) -> str:
    claims = {
        "type": TOKEN_TYPE,
        "provider": pending.provider,
        "state": pending.state,
        "verifier": pending.verifier,
        "iat": now,
        "exp": now + PENDING_LIFETIME,
    }

    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def open_pending(sealed: str, secret: str) -> PendingSignIn | None:
    options: Options = {"require": ["type", "provider", "state", "verifier", "iat", "exp"]}

    try:
        claims = jwt.decode(sealed, secret, algorithms=[ALGORITHM], options=options)
    except jwt.InvalidTokenError:
        return None

    if claims["type"] != TOKEN_TYPE:
        return None

    return PendingSignIn(
        provider=claims["provider"],
        state=claims["state"],
        verifier=claims["verifier"],
    )
