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


class OAuthProviderNotEnabled(DomainError):
    code = "OAUTH_PROVIDER_NOT_ENABLED"
    status = 404
    message = "That sign-in provider is not configured on this instance."


# Never leaves as JSON: the OAuth callback answers with a redirect carrying the
# code. The message is the reason, for the log.
class OAuthFailed(DomainError):
    code = "OAUTH_FAILED"
    status = 400
    message = "The sign-in with the provider did not complete."


class SandboxUnavailable(DomainError):
    code = "SANDBOX_UNAVAILABLE"
    status = 503
    message = "A kernel could not be started."


class ModelNotFound(DomainError):
    code = "MODEL_NOT_FOUND"
    status = 404
    message = "No such model."


class ConversationNotFound(DomainError):
    code = "CONVERSATION_NOT_FOUND"
    status = 404
    message = "No such conversation."


# The same code the 422 handler uses for a malformed request, for input that is
# well-formed JSON but still unacceptable — a file name with a slash in it.
class InvalidInput(DomainError):
    code = "VALIDATION_ERROR"
    status = 422
    message = "The request is missing or malformed."


class ConversationBusy(DomainError):
    code = "CONVERSATION_BUSY"
    status = 409
    message = "A run is already in progress in this conversation."


class FileNotFound(DomainError):
    code = "FILE_NOT_FOUND"
    status = 404
    message = "No such file."


class FileAlreadyExists(DomainError):
    code = "FILE_ALREADY_EXISTS"
    status = 409
    message = "The conversation already has a file with that name."


class FileTooLarge(DomainError):
    code = "FILE_TOO_LARGE"
    status = 413
    message = "The file is over this instance's upload limit."


class UnsupportedFileType(DomainError):
    code = "UNSUPPORTED_FILE_TYPE"
    status = 415
    message = "Only CSV, TSV, Excel and Parquet files are accepted."


class ModelManagedByEnvironment(DomainError):
    code = "MODEL_MANAGED_BY_ENVIRONMENT"
    status = 409
    message = "This model comes from the instance's environment and cannot be changed here."
