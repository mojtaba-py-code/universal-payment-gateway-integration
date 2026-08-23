"""Domain error taxonomy and standardized error envelope.

Every failure surfaced to a client is expressed as a stable, machine-readable
``code`` plus a human message and optional structured ``details``. This keeps
the public API contract predictable and lets integrators branch on codes rather
than parsing prose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable error codes. Never renumber — clients depend on these."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RATE_LIMITED = "rate_limited"
    INVALID_STATE = "invalid_state"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CIRCUIT_OPEN = "circuit_open"
    SIGNATURE_INVALID = "signature_invalid"
    REPLAY_DETECTED = "replay_detected"
    UNSUPPORTED_CURRENCY = "unsupported_currency"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INTERNAL_ERROR = "internal_error"


class DomainError(Exception):
    """Base class for all expected, mapped application errors."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        code: ErrorCode | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status

    def to_envelope(self, correlation_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        if correlation_id:
            body["error"]["correlation_id"] = correlation_id
        return body


class ValidationError(DomainError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 422


class AuthenticationError(DomainError):
    code = ErrorCode.AUTHENTICATION_FAILED
    http_status = 401


class PermissionDeniedError(DomainError):
    code = ErrorCode.PERMISSION_DENIED
    http_status = 403


class NotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class ConflictError(DomainError):
    code = ErrorCode.CONFLICT
    http_status = 409


class IdempotencyConflictError(DomainError):
    code = ErrorCode.IDEMPOTENCY_CONFLICT
    http_status = 409


class RateLimitedError(DomainError):
    code = ErrorCode.RATE_LIMITED
    http_status = 429


class InvalidStateError(DomainError):
    """A payment/refund transition that violates the state machine."""

    code = ErrorCode.INVALID_STATE
    http_status = 409


class UnsupportedCurrencyError(DomainError):
    code = ErrorCode.UNSUPPORTED_CURRENCY
    http_status = 422


class ProviderError(DomainError):
    """A downstream provider rejected or failed the operation."""

    code = ErrorCode.PROVIDER_ERROR
    http_status = 502


class ProviderUnavailableError(DomainError):
    code = ErrorCode.PROVIDER_UNAVAILABLE
    http_status = 503


class CircuitOpenError(ProviderUnavailableError):
    code = ErrorCode.CIRCUIT_OPEN


class SignatureInvalidError(DomainError):
    code = ErrorCode.SIGNATURE_INVALID
    http_status = 400


class ReplayDetectedError(DomainError):
    code = ErrorCode.REPLAY_DETECTED
    http_status = 400
