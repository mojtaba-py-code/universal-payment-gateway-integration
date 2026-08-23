"""Health & readiness probes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready", summary="Readiness probe")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - exercised only on real DB outage
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    return JSONResponse({"status": "ready", "database": "up"})
