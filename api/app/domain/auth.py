"""The shapes of signing up, signing in and the account, as api.md defines them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# Length is the only rule — no required digits or symbols, which push people
# towards predictable passwords rather than long ones.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Emails need no ceiling of their own: email-validator refuses anything over the
# RFC's 254 characters, which fits the users.email column.


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


# No minimum here: a short password at login is a wrong password, and saying
# INVALID_CREDENTIALS about it is more honest than a validation error. Above the
# ceiling no password can exist, so that one is refused before any hashing.
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class AuthOptions(BaseModel):
    registration_open: bool
    oauth: list[str]


class User(BaseModel):
    id: UUID
    email: str
    created_at: datetime


class Account(BaseModel):
    id: UUID
    email: str
    has_password: bool
    oauth: list[str]
    created_at: datetime


class AccessToken(BaseModel):
    access_token: str
    expires_at: datetime


@dataclass(frozen=True)
class SignedIn:
    """What signing in or refreshing produces: one part for the body, one for the cookie."""

    access: AccessToken
    refresh_token: str
    refresh_expires_at: datetime
