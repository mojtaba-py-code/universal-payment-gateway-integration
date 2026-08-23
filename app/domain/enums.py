"""Enumerations shared across the domain, persistence, and API layers."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Coarse-grained RBAC roles. Fine-grained access derives from scopes."""

    ADMIN = "admin"
    MERCHANT = "merchant"
    VIEWER = "viewer"


class PaymentStatus(StrEnum):
    """Lifecycle states of a payment. Transitions are enforced by the engine."""

    REQUIRES_CONFIRMATION = "requires_confirmation"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    CANCELED = "canceled"
    FAILED = "failed"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CaptureMethod(StrEnum):
    """Whether funds are captured immediately or authorized for later capture."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


class PaymentMethodType(StrEnum):
    CARD = "card"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    BANK_TRANSFER = "bank_transfer"
    SEPA = "sepa"
    ACH = "ach"
    WIRE = "wire"
    WALLET = "wallet"
    CRYPTO = "crypto"
    QR = "qr"
    BNPL = "bnpl"


class ProviderName(StrEnum):
    """Identifiers for registered provider adapters."""

    MOCK = "mock"
    STRIPE = "stripe"


class WebhookStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class AuditAction(StrEnum):
    USER_REGISTERED = "user.registered"
    USER_LOGIN = "user.login"
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    PAYMENT_CREATED = "payment.created"
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_CANCELED = "payment.canceled"
    PAYMENT_FAILED = "payment.failed"
    REFUND_CREATED = "refund.created"
    WEBHOOK_RECEIVED = "webhook.received"
