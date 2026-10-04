"""Account password hashing.

Argon2id, deliberately slow: a password is short and guessable, so the defence
is making each attempt expensive. The parameters travel inside the hash string
itself, which is why no column stores them.

The encoded form looks like:

    $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Verifying a password that belongs to nobody must cost the same as verifying a
# real one, or the response time says whether an email is registered. This is a
# hash of a value no one can produce.
_DUMMY = _hasher.hash("this hash exists only to be compared against")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except VerifyMismatchError, VerificationError, InvalidHashError:
        return False


def waste_time() -> None:
    """Spend a verification's worth of time on nothing.

    Called on the paths where there is no stored hash to check against, so that
    "no such account" and "wrong password" take the same wall clock.
    """
    verify_password("", _DUMMY)
