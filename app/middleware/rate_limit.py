"""Rate-limiting middleware.

Applies a per-identity request quota. The identity is the authenticated API key
/ bearer subject when present, otherwise the client IP. Health, metrics, and
documentation endpoints are exempt so probes and dashboards are never throttled.

On limit breach it returns a standardized ``429`` error envelope with a
``Retry-After`` header.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import ErrorCode
from app.core.rate_limit import RateLimiter

_EXEMPT_PREFIXES = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, limiter: RateLimiter) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = limiter

    def _identity(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            return f"key:{api_key[:16]}"
        if auth:
            return f"bearer:{auth[-16:]}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        result = self._limiter.hit(self._identity(request))
        if not result.allowed:
            correlation_id = getattr(request.state, "correlation_id", None)
            body = {
                "error": {
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": "rate limit exceeded",
                    "details": {"retry_after": result.retry_after},
                }
            }
            if correlation_id:
                body["error"]["correlation_id"] = correlation_id
            return JSONResponse(
                body, status_code=429, headers={"Retry-After": str(result.retry_after)}
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response
