"""Authentication & credential service.

Owns user registration, password authentication (with basic brute-force
lockout), JWT issuance/refresh, and API-key lifecycle. All persistence goes
through repositories; all security-relevant events are audited.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.db.models.api_key import ApiKey
from app.db.models.user import User
from app.domain.enums import AuditAction, UserRole
from app.domain.rbac import scopes_for_role
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.users import UserRepository
from app.security import api_keys as api_key_utils
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import TokenService
from app.services.audit import AuditService

_MAX_FAILED_LOGINS = 10


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type label, not a secret


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    api_key: ApiKey
    plaintext: str


class AuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepository,
        api_keys: ApiKeyRepository,
        audit: AuditService,
        tokens: TokenService,
    ) -> None:
        self._settings = settings
        self._users = users
        self._api_keys = api_keys
        self._audit = audit
        self._tokens = tokens

    # -- Registration & login --------------------------------------------------
    async def register(
        self,
        email: str,
        password: str,
        *,
        full_name: str | None = None,
        role: UserRole = UserRole.MERCHANT,
    ) -> User:
        email = email.lower().strip()
        if await self._users.email_exists(email):
            raise ConflictError("an account with this email already exists")
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )
        self._users.add(user)
        await self._users.flush()
        self._audit.record(
            AuditAction.USER_REGISTERED,
            actor_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(email.lower().strip())
        # Always run a hash verification to keep timing uniform whether or not the
        # user exists, mitigating user-enumeration via response timing.
        reference_hash = (
            user.hashed_password
            if user is not None
            else "$argon2id$v=19$m=65536,t=3,p=2$" + "A" * 22 + "$" + "A" * 43
        )
        password_ok = verify_password(password, reference_hash)

        if user is None or not password_ok:
            if user is not None:
                user.failed_login_attempts += 1
            raise AuthenticationError("invalid email or password")

        if not user.is_active or user.failed_login_attempts >= _MAX_FAILED_LOGINS:
            raise AuthenticationError("account is locked; contact support")

        # Successful login: reset counter and transparently upgrade the hash if
        # the Argon2 parameters have since been strengthened.
        user.failed_login_attempts = 0
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)
        self._audit.record(
            AuditAction.USER_LOGIN, actor_id=user.id, resource_type="user", resource_id=str(user.id)
        )
        return user

    # -- Tokens ----------------------------------------------------------------
    def issue_tokens(self, user: User) -> TokenPair:
        scopes = scopes_for_role(user.role)
        return TokenPair(
            access_token=self._tokens.create_access_token(str(user.id), scopes),
            refresh_token=self._tokens.create_refresh_token(str(user.id)),
        )

    async def user_from_access_token(self, token: str) -> User:
        import uuid

        claims = self._tokens.decode(token, expected_type="access")
        user = await self._users.get(uuid.UUID(claims.subject))
        if user is None or not user.is_active:
            raise AuthenticationError("user not found or inactive")
        return user

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._tokens.decode(refresh_token, expected_type="refresh")
        import uuid

        user = await self._users.get(uuid.UUID(claims.subject))
        if user is None or not user.is_active:
            raise AuthenticationError("user no longer active")
        return self.issue_tokens(user)

    # -- API keys --------------------------------------------------------------
    async def create_api_key(self, user: User, name: str) -> IssuedApiKey:
        generated = api_key_utils.generate_api_key(self._settings.api_key_prefix)
        record = ApiKey(
            user_id=user.id,
            name=name,
            hashed_key=generated.lookup_hash,
            display_prefix=generated.display_prefix,
        )
        self._api_keys.add(record)
        await self._api_keys.flush()
        self._audit.record(
            AuditAction.API_KEY_CREATED,
            actor_id=user.id,
            resource_type="api_key",
            resource_id=str(record.id),
        )
        return IssuedApiKey(api_key=record, plaintext=generated.full_key)

    async def authenticate_api_key(self, presented_key: str) -> User:
        lookup = api_key_utils.hash_for_lookup(presented_key)
        record = await self._api_keys.get_by_hash(lookup)
        if record is None or not record.is_active or record.revoked_at is not None:
            raise AuthenticationError("invalid API key")
        user = await self._users.get(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("API key owner is inactive")
        from datetime import UTC, datetime

        record.last_used_at = datetime.now(UTC)
        return user

    async def list_api_keys(self, user: User) -> list[ApiKey]:
        return list(await self._api_keys.list_for_owner(user.id))

    async def revoke_api_key(self, user: User, key_id: str) -> None:
        import uuid
        from datetime import UTC, datetime

        record = await self._api_keys.get(uuid.UUID(key_id))
        if record is None or record.user_id != user.id:
            raise NotFoundError("API key not found")
        record.is_active = False
        record.revoked_at = datetime.now(UTC)
        self._audit.record(
            AuditAction.API_KEY_REVOKED,
            actor_id=user.id,
            resource_type="api_key",
            resource_id=key_id,
        )
