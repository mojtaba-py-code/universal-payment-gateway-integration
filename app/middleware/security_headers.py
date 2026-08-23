"""Security-headers middleware.

Applies a conservative set of hardening headers to every response. These defend
against clickjacking, MIME-sniffing, referrer leakage, and (for any HTML the API
might serve, e.g. docs) a strict content-security policy. HSTS is emitted so
that behind TLS the browser refuses to downgrade to HTTP.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "0",  # modern browsers rely on CSP; legacy filter disabled
    # Locked down, but permits the Swagger/ReDoc assets served from jsDelivr.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "connect-src 'self'; frame-ancestors 'none'"
    ),
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _HEADERS.items():
            response.headers.setdefault(header, value)
        return response
