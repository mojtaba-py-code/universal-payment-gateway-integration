"""Payment provider adapters and the plugin registry.

Importing this package registers the built-in providers on the global registry
as a side effect, so :func:`app.providers.registry.build_provider` can resolve
them by name.
"""

from __future__ import annotations

# Registering imports — keep these; they populate the provider registry.
from app.providers import mock, stripe

__all__ = ["mock", "stripe"]
