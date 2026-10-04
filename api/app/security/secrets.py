"""Encrypting the secrets that must come back: provider API keys today, database
connector credentials later (decision 5).

AES-256-GCM. The key never reaches the database — it comes from the environment
and lives only in the process.

Stored form:

    v1.<nonce>.<ciphertext>

both parts base64url without padding. The nonce is not a secret; it travels
alongside because decryption needs it. What matters is that it is never reused
with the same key, which is why a fresh one is drawn for every single value.

The `v1.` prefix is what allows changing algorithm later without having to guess
how to read what is already stored.
"""

from __future__ import annotations

import base64
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12


# What a stored key shows of itself: enough to tell two keys apart, never enough
# to use one.
HINT_CHARACTERS = 4


class DecryptionFailed(Exception):
    """The stored value could not be opened with this key."""


def _encode(raw: bytes) -> str:
    encoded = base64.urlsafe_b64encode(raw)
    return encoded.decode().rstrip("=")


# urlsafe_b64decode takes no validate flag, so the two url-safe characters are
# translated back by hand and the strict decoder does the rest. Without
# validate=True, base64 quietly drops anything outside the alphabet and junk
# decodes to a short string instead of failing.
_URLSAFE_TO_STANDARD = str.maketrans("-_", "+/")


def _decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    standard = (text + padding).translate(_URLSAFE_TO_STANDARD)

    return base64.b64decode(standard, validate=True)


def decode_key(encoded: str) -> bytes:
    """Turns the SECRETS_KEY environment value into raw bytes."""
    try:
        key = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("SECRETS_KEY is not valid base64") from exc

    if len(key) != KEY_BYTES:
        raise ValueError(f"SECRETS_KEY must decode to {KEY_BYTES} bytes, got {len(key)}")

    return key


class Cipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError(f"key must be {KEY_BYTES} bytes, got {len(key)}")

        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)

        return f"{VERSION}.{_encode(nonce)}.{_encode(ciphertext)}"

    def decrypt(self, envelope: str) -> str:
        parts = envelope.split(".")
        if len(parts) != 3:
            raise DecryptionFailed("stored value is not in the v1.<nonce>.<ciphertext> form")

        version, nonce_text, ciphertext_text = parts
        if version != VERSION:
            raise DecryptionFailed(f"unknown envelope version {version!r}")

        try:
            nonce = _decode(nonce_text)
            ciphertext = _decode(ciphertext_text)
        except (ValueError, TypeError) as exc:
            raise DecryptionFailed("stored value is not valid base64") from exc

        if len(nonce) != NONCE_BYTES:
            raise DecryptionFailed(f"nonce must be {NONCE_BYTES} bytes, got {len(nonce)}")

        # GCM authenticates as well as encrypts: a single altered byte fails
        # here rather than returning plausible rubbish.
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise DecryptionFailed("wrong key, or the stored value was altered") from exc

        return plaintext.decode()


def key_hint(key: str | None) -> str | None:
    """ "…x9Qa" — the last four characters, or None when there is no key. A key
    too short to spare four characters shows none of them."""
    if key is None:
        return None

    if len(key) < 2 * HINT_CHARACTERS:
        return "…"

    return "…" + key[-HINT_CHARACTERS:]
