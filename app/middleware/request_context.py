"""Request-context middleware.

Assigns (or propagates) a correlation id per request, binds it to the logging
context var, records RED metrics, and echoes it back in the ``X-Correlation-ID``
response header so clients and log aggregators can trace a request end to end.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import correlation_id_var
from app.core.metrics import http_request_duration_seconds, http_requests_total

_HEADER = "X-Correlation-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(_HEADER)
        correlation_id = incoming or uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        request.state.correlation_id = correlation_id

        # Use the route template (not the raw path) as the metric label to avoid
        # unbounded cardinality from path parameters like payment ids.
        started = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_HEADER] = correlation_id
            return response
        finally:
            elapsed = time.monotonic() - started
            path_label = _route_label(request)
            http_requests_total.labels(
                method=request.method, path=path_label, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(method=request.method, path=path_label).observe(
                elapsed
            )
            correlation_id_var.reset(token)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)
