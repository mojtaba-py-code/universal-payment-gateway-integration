"""Exception handlers that render every error as the standard envelope.

Mapping happens in one place so the public error contract is consistent:
``{"error": {"code", "message", "details?", "correlation_id?"}}``. Unexpected
exceptions are logged with their correlation id and returned as a generic 500 —
internal details are never leaked to clients.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DomainError, ErrorCode
from app.core.logging import correlation_id_var, get_logger

_log = get_logger("errors")


def _envelope(code: str, message: str, *, details: dict | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    cid = correlation_id_var.get()
    if cid:
        body["error"]["correlation_id"] = cid
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            _envelope(exc.code.value, exc.message, details=exc.details or None),
            status_code=exc.http_status,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Build a JSON-safe view of the errors. Pydantic may embed the original
        # ``ValueError`` object under ``ctx`` (from custom validators), which is
        # not serialisable — so we project only the safe fields.
        errors = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            _envelope(
                ErrorCode.VALIDATION_ERROR.value,
                "request validation failed",
                details={"errors": errors},
            ),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = (
            ErrorCode.NOT_FOUND.value if exc.status_code == 404 else ErrorCode.INTERNAL_ERROR.value
        )
        return JSONResponse(_envelope(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        _log.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        return JSONResponse(
            _envelope(ErrorCode.INTERNAL_ERROR.value, "an unexpected error occurred"),
            status_code=500,
        )
