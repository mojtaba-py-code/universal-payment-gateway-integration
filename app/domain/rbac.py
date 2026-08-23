"""Role-based access control: mapping roles to fine-grained scopes.

Scopes are the unit of authorization checked at the API boundary. Roles are a
convenient bundle of scopes. Keeping the mapping in one place makes the security
model auditable and easy to extend without touching endpoint code.
"""

from __future__ import annotations

from app.domain.enums import UserRole

# Fine-grained permission scopes.
SCOPE_PAYMENTS_READ = "payments:read"
SCOPE_PAYMENTS_WRITE = "payments:write"
SCOPE_REFUNDS_WRITE = "refunds:write"
SCOPE_PROVIDERS_MANAGE = "providers:manage"
SCOPE_ADMIN = "admin:all"

_ROLE_SCOPES: dict[UserRole, tuple[str, ...]] = {
    UserRole.ADMIN: (
        SCOPE_ADMIN,
        SCOPE_PAYMENTS_READ,
        SCOPE_PAYMENTS_WRITE,
        SCOPE_REFUNDS_WRITE,
        SCOPE_PROVIDERS_MANAGE,
    ),
    UserRole.MERCHANT: (
        SCOPE_PAYMENTS_READ,
        SCOPE_PAYMENTS_WRITE,
        SCOPE_REFUNDS_WRITE,
        SCOPE_PROVIDERS_MANAGE,
    ),
    UserRole.VIEWER: (SCOPE_PAYMENTS_READ,),
}


def scopes_for_role(role: UserRole) -> tuple[str, ...]:
    return _ROLE_SCOPES.get(role, ())


def has_scope(granted: tuple[str, ...], required: str) -> bool:
    """True if ``required`` is satisfied by ``granted`` (``admin:all`` is a wildcard)."""
    return SCOPE_ADMIN in granted or required in granted
