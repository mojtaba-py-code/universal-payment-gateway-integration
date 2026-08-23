"""Shared schema building blocks."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MoneyOut(BaseModel):
    """Serialised money: minor units + currency + a human-readable decimal."""

    minor_units: int
    currency: str
    display: str


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str = Field(examples=["ok"])
