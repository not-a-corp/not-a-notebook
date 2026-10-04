"""The failures this API can report.

Every one carries the ``code`` the client branches on and the status it maps to,
so the catalogue lives in one place instead of being spread across routes. The
codes themselves are the contract in api.md; a class is added here when the first
use case raises it.

Codes say what the caller did, never what the system found: a wrong email and a
wrong password are both ``INVALID_CREDENTIALS``, because telling them apart would
hand a stranger the list of registered emails.
"""

from __future__ import annotations


class DomainError(Exception):
    code: str = "INTERNAL_ERROR"
    status: int = 500
    message: str = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message

        super().__init__(self.message)


class Unauthenticated(DomainError):
    code = "UNAUTHENTICATED"
    status = 401
    message = "Missing, invalid or expired credentials."


class InvalidCredentials(DomainError):
    code = "INVALID_CREDENTIALS"
    status = 401
    message = "Wrong email or password."


class RegistrationClosed(DomainError):
    code = "REGISTRATION_CLOSED"
    status = 403
    message = "This instance does not accept new accounts."


class EmailAlreadyRegistered(DomainError):
    code = "EMAIL_ALREADY_REGISTERED"
    status = 409
    message = "That email already has an account."
