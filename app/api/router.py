"""Aggregate the versioned API routers into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, payments, refunds, webhooks

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(payments.router)
api_v1_router.include_router(refunds.router)
api_v1_router.include_router(webhooks.router)
api_v1_router.include_router(admin.router)
