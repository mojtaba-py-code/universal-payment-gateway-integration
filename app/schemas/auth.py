"""Auth & API-key schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128, examples=["Sup3r-Secret-Pass"])
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type label, not a secret


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120, examples=["production-server"])


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreatedResponse(ApiKeyResponse):
    #: The full secret — shown exactly once, at creation time.
    api_key: str
