"""Authentication, user, and API-key endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_auth_service
from app.schemas.auth import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, auth: AuthDep) -> UserResponse:
    user = await auth.register(payload.email, payload.password, full_name=payload.full_name)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, auth: AuthDep) -> TokenResponse:
    user = await auth.authenticate(payload.email, payload.password)
    tokens = auth.issue_tokens(user)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, auth: AuthDep) -> TokenResponse:
    tokens = await auth.refresh(payload.refresh_token)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest, user: CurrentUser, auth: AuthDep
) -> ApiKeyCreatedResponse:
    issued = await auth.create_api_key(user, payload.name)
    return ApiKeyCreatedResponse(
        id=issued.api_key.id,
        name=issued.api_key.name,
        display_prefix=issued.api_key.display_prefix,
        is_active=issued.api_key.is_active,
        created_at=issued.api_key.created_at,
        last_used_at=issued.api_key.last_used_at,
        api_key=issued.plaintext,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(user: CurrentUser, auth: AuthDep) -> list[ApiKeyResponse]:
    keys = await auth.list_api_keys(user)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: str, user: CurrentUser, auth: AuthDep) -> None:
    await auth.revoke_api_key(user, key_id)
