"""Dependency injection wiring.

FastAPI's ``Depends`` graph is our composition root. Each request gets a
transactional database session; repositories and services are constructed on top
of it. Process-level singletons (settings, token service, gateway manager, secret
box) live on ``app.state`` and are injected read-only.

Authentication accepts either a Bearer JWT (``Authorization: Bearer …``) or an
API key (``X-API-Key: …``). Authorization is enforced with scope dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.db.models.user import User
from app.domain.rbac import has_scope, scopes_for_role
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.audit import AuditRepository, ProviderConfigRepository
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.payments import PaymentRepository
from app.repositories.refunds import RefundRepository
from app.repositories.users import UserRepository
from app.repositories.webhooks import WebhookRepository
from app.security.tokens import TokenService
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.gateway_manager import GatewayManager
from app.services.idempotency import IdempotencyService
from app.services.payments import PaymentService
from app.services.refunds import RefundService
from app.services.webhooks import WebhookService


# --------------------------------------------------------------------------- #
# Process-level singletons (from app.state)                                    #
# --------------------------------------------------------------------------- #
def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_service


def get_gateway_manager(request: Request) -> GatewayManager:
    return request.app.state.gateway_manager


# --------------------------------------------------------------------------- #
# Request-scoped database session (unit of work)                              #
# --------------------------------------------------------------------------- #
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    session: AsyncSession = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# --------------------------------------------------------------------------- #
# Repositories                                                                 #
# --------------------------------------------------------------------------- #
def get_audit_service(session: SessionDep) -> AuditService:
    return AuditService(AuditRepository(session))


def get_auth_service(
    session: SessionDep,
    settings: SettingsDep,
    tokens: Annotated[TokenService, Depends(get_token_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthService:
    return AuthService(
        settings=settings,
        users=UserRepository(session),
        api_keys=ApiKeyRepository(session),
        audit=audit,
        tokens=tokens,
    )


def get_payment_service(
    session: SessionDep,
    gateway: Annotated[GatewayManager, Depends(get_gateway_manager)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> PaymentService:
    return PaymentService(
        payments=PaymentRepository(session),
        provider_configs=ProviderConfigRepository(session),
        gateway=gateway,
        audit=audit,
    )


def get_refund_service(
    session: SessionDep,
    gateway: Annotated[GatewayManager, Depends(get_gateway_manager)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> RefundService:
    return RefundService(
        payments=PaymentRepository(session),
        refunds=RefundRepository(session),
        provider_configs=ProviderConfigRepository(session),
        gateway=gateway,
        audit=audit,
    )


def get_webhook_service(
    session: SessionDep,
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> WebhookService:
    return WebhookService(repo=WebhookRepository(session), audit=audit)


def get_idempotency_service(session: SessionDep) -> IdempotencyService:
    return IdempotencyService(IdempotencyRepository(session))


# --------------------------------------------------------------------------- #
# Authentication & authorization                                               #
# --------------------------------------------------------------------------- #
async def get_current_user(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return await auth.authenticate_api_key(api_key)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return await auth.user_from_access_token(token)

    raise AuthenticationError("missing authentication credentials")


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_scope(scope: str) -> Callable[..., Awaitable[User]]:
    """Return a dependency enforcing that the current user holds ``scope``."""

    async def _dependency(user: CurrentUser) -> User:
        if not has_scope(scopes_for_role(user.role), scope):
            raise PermissionDeniedError("insufficient scope", details={"required_scope": scope})
        return user

    return _dependency
