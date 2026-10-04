"""AES-256-GCM for stored provider keys, the envelope the database stores, and the
hint the API shows instead of a key."""

from __future__ import annotations

import base64
import secrets

import pytest
from app.security.secrets import (
    KEY_BYTES,
    NONCE_BYTES,
    Cipher,
    DecryptionFailed,
    decode_key,
    key_hint,
)

SECRET = "sk-ant-api03-K7mQ2vXpL9x9Qa"


@pytest.fixture
def cipher() -> Cipher:
    key = secrets.token_bytes(KEY_BYTES)
    return Cipher(key)


def test_a_value_comes_back_out(cipher: Cipher) -> None:
    stored = cipher.encrypt(SECRET)

    assert cipher.decrypt(stored) == SECRET


def test_the_stored_form_is_the_documented_envelope(cipher: Cipher) -> None:
    stored = cipher.encrypt(SECRET)

    version, nonce, ciphertext = stored.split(".")

    assert version == "v1"
    assert nonce
    assert ciphertext


def test_the_plaintext_is_nowhere_in_the_stored_form(cipher: Cipher) -> None:
    stored = cipher.encrypt(SECRET)

    assert SECRET not in stored


def test_the_same_value_encrypts_differently_every_time(cipher: Cipher) -> None:
    """A reused nonce breaks GCM badly, so each value draws a fresh one."""
    first = cipher.encrypt(SECRET)
    second = cipher.encrypt(SECRET)

    assert first != second
    assert cipher.decrypt(first) == cipher.decrypt(second) == SECRET


def test_the_nonce_is_the_right_size(cipher: Cipher) -> None:
    stored = cipher.encrypt(SECRET)
    _, nonce_text, _ = stored.split(".")

    padding = "=" * (-len(nonce_text) % 4)
    nonce = base64.urlsafe_b64decode(nonce_text + padding)

    assert len(nonce) == NONCE_BYTES


def test_an_altered_byte_is_refused(cipher: Cipher) -> None:
    """GCM authenticates: tampering fails loudly instead of returning rubbish."""
    version, nonce, ciphertext = cipher.encrypt(SECRET).split(".")
    flipped = "A" if ciphertext[0] != "A" else "B"
    tampered = f"{version}.{nonce}.{flipped}{ciphertext[1:]}"

    with pytest.raises(DecryptionFailed):
        cipher.decrypt(tampered)


def test_another_key_cannot_open_it(cipher: Cipher) -> None:
    stored = cipher.encrypt(SECRET)
    stranger = Cipher(secrets.token_bytes(KEY_BYTES))

    with pytest.raises(DecryptionFailed):
        stranger.decrypt(stored)


@pytest.mark.parametrize(
    "stored",
    [
        "not-an-envelope",
        "v1.only-two-parts",
        "v2.abc.def",
        "v1.!!!.???",
    ],
)
def test_a_malformed_envelope_is_refused(cipher: Cipher, stored: str) -> None:
    with pytest.raises(DecryptionFailed):
        cipher.decrypt(stored)


def test_an_empty_value_round_trips(cipher: Cipher) -> None:
    stored = cipher.encrypt("")

    assert cipher.decrypt(stored) == ""


def test_a_long_note_round_trips(cipher: Cipher) -> None:
    note = "a" * 10_000
    stored = cipher.encrypt(note)

    assert cipher.decrypt(stored) == note


def test_a_key_of_the_wrong_size_is_refused() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Cipher(secrets.token_bytes(16))


def test_the_environment_key_must_be_base64() -> None:
    with pytest.raises(ValueError, match="base64"):
        decode_key("this is not base64!!!")


def test_the_environment_key_must_decode_to_32_bytes() -> None:
    short = base64.b64encode(secrets.token_bytes(16)).decode()

    with pytest.raises(ValueError, match="32 bytes"):
        decode_key(short)


def test_a_good_environment_key_decodes() -> None:
    encoded = base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode()

    assert len(decode_key(encoded)) == KEY_BYTES


def test_a_hint_shows_the_last_four_characters_only() -> None:
    assert key_hint(SECRET) == "…x9Qa"


def test_no_key_has_no_hint() -> None:
    assert key_hint(None) is None


def test_a_key_too_short_to_spare_four_characters_shows_none() -> None:
    assert key_hint("abc123") == "…"
