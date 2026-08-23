"""Prometheus metrics.

A small, curated set of RED-style metrics (Rate, Errors, Duration) plus
payment-domain counters. Using a dedicated registry keeps the app testable and
avoids leaking metrics between test cases.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "upgi_http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "upgi_http_request_duration_seconds",
    "HTTP request latency.",
    labelnames=("method", "path"),
    registry=REGISTRY,
)

payment_operations_total = Counter(
    "upgi_payment_operations_total",
    "Payment operations by type and outcome.",
    labelnames=("operation", "provider", "outcome"),
    registry=REGISTRY,
)

provider_calls_total = Counter(
    "upgi_provider_calls_total",
    "Outbound provider API calls by provider and outcome.",
    labelnames=("provider", "outcome"),
    registry=REGISTRY,
)

provider_call_duration_seconds = Histogram(
    "upgi_provider_call_duration_seconds",
    "Latency of outbound provider calls.",
    labelnames=("provider",),
    registry=REGISTRY,
)

webhook_events_total = Counter(
    "upgi_webhook_events_total",
    "Inbound webhook events by provider and outcome.",
    labelnames=("provider", "outcome"),
    registry=REGISTRY,
)
