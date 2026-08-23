"""Rate limiting.

A small abstraction with a dependency-free in-memory implementation (fixed
window) suitable for single-process/local use and tests. In production behind
multiple workers, swap in a Redis-backed limiter — the interface is identical,
which is why the middleware depends on :class:`RateLimiter`, not a concrete type.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter(Protocol):
    def hit(self, key: str) -> RateLimitResult: ...


class InMemoryRateLimiter:
    """Fixed-window counter. Thread-safe for the sync ASGI path."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._now = now
        self._lock = threading.Lock()
        # key -> (window_start, count)
        self._buckets: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> RateLimitResult:
        now = self._now()
        with self._lock:
            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= self._window:
                window_start, count = now, 0
            count += 1
            self._buckets[key] = (window_start, count)
            remaining = max(0, self._limit - count)
            if count > self._limit:
                retry_after = int(self._window - (now - window_start)) + 1
                return RateLimitResult(allowed=False, remaining=0, retry_after=retry_after)
            return RateLimitResult(allowed=True, remaining=remaining, retry_after=0)
