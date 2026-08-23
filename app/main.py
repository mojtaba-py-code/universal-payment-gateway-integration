"""Application factory and composition root.

``create_app`` builds a fully wired FastAPI application: configuration, logging,
database engine, security services, the gateway manager, middleware stack,
routers, metrics, and error handlers. Keeping construction in a factory makes the
app trivially testable — tests build an isolated instance with overridden
settings and an in-memory database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import PlainTextResponse

from app import __version__
from app.api.error_handlers import register_exception_handlers
from app.api.router import api_v1_router
from app.api.v1 import health
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import REGISTRY
from app.core.rate_limit import InMemoryRateLimiter
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.security.crypto import SecretBox
from app.security.tokens import TokenService
from app.services.gateway_manager import GatewayManager

_log = get_logger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    settings.assert_production_ready()

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    secret_box = SecretBox.from_single_key(settings.encryption_key_bytes())
    token_service = TokenService(settings)
    http_client = httpx.AsyncClient(timeout=settings.outbound_http_timeout_seconds)
    gateway_manager = GatewayManager(
        settings=settings, secret_box=secret_box, http_client=http_client
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Auto-create schema for non-production convenience; production uses Alembic.
        if not settings.is_production:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        _log.info("startup", environment=settings.environment.value, version=__version__)
        try:
            yield
        finally:
            await http_client.aclose()
            await engine.dispose()
            _log.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "A unified, provider-agnostic payment orchestration API. "
            "One interface for many payment gateways."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # -- Shared state ----------------------------------------------------------
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.secret_box = secret_box
    app.state.token_service = token_service
    app.state.http_client = http_client
    app.state.gateway_manager = gateway_manager

    # -- Middleware (added inner-first; last added is outermost) ---------------
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.rate_limit_enabled:
        limiter = InMemoryRateLimiter(
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Routers ---------------------------------------------------------------
    app.include_router(health.router)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["meta"], summary="Service metadata")
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": "/health/live",
        }

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> PlainTextResponse:
            return PlainTextResponse(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    register_exception_handlers(app)
    return app
