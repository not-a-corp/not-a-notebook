"""Access tokens: short-lived JWTs, checked without touching the database.

The token says who the caller is (`sub`, the user's external id) and until when.
Nothing else rides in it — a JWT is signed, not encrypted, and anyone holding one
can read its claims.

The `type` claim is there so that no other token this service may sign one day
(an OAuth state, an email link) can ever be passed off as an access token.

The cost, accepted in the plan: a token outlives a sign-out or a password change
by up to its fifteen minutes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import jwt
from jwt.types import Options

from app.domain.auth import AccessToken

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
ALGORITHM = "HS256"
TOKEN_TYPE = "access"


def issue_access_token(user_id: UUID, secret: str, now: datetime) -> AccessToken:
    # Whole seconds: `exp` is an integer in the token, and the body's expires_at
    # must say the same instant the token does.
    issued_at = now.replace(microsecond=0)
    expires_at = issued_at + ACCESS_TOKEN_LIFETIME

    claims = {
        "sub": str(user_id),
        "type": TOKEN_TYPE,
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(claims, secret, algorithm=ALGORITHM)

    return AccessToken(access_token=token, expires_at=expires_at)


def read_access_token(token: str, secret: str) -> UUID | None:
    """The user the token speaks for, or None if it is not a valid access token.

    `algorithms` is a list of one on purpose: accepting whatever the token's own
    header names is how "alg: none" tokens get through.
    """
    options: Options = {"require": ["sub", "type", "iat", "exp"]}

    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options=options)
    except jwt.InvalidTokenError:
        return None

    if claims["type"] != TOKEN_TYPE:
        return None

    try:
        user_id = UUID(claims["sub"])
    except TypeError, ValueError:
        return None

    return user_id
