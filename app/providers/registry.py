"""Provider registry + factory (the Plugin architecture seam).

Adapters register themselves via the :func:`register_provider` decorator. The
:func:`build_provider` factory resolves a :class:`ProviderName` to a live adapter
instance bound to a :class:`ProviderContext`. New providers become available by
importing a module that registers them — no edits to existing code.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.errors import ProviderError
from app.domain.enums import ProviderName
from app.providers.base import BasePaymentProvider, ProviderContext

_REGISTRY: dict[ProviderName, type[BasePaymentProvider]] = {}


def register_provider(
    name: ProviderName,
) -> Callable[[type[BasePaymentProvider]], type[BasePaymentProvider]]:
    """Class decorator that registers an adapter under ``name``."""

    def _decorator(cls: type[BasePaymentProvider]) -> type[BasePaymentProvider]:
        if name in _REGISTRY:
            raise RuntimeError(f"provider {name!r} is already registered")
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return _decorator


def available_providers() -> tuple[ProviderName, ...]:
    return tuple(_REGISTRY.keys())


def is_registered(name: ProviderName) -> bool:
    return name in _REGISTRY


def build_provider(name: ProviderName, context: ProviderContext) -> BasePaymentProvider:
    """Instantiate the adapter registered under ``name``."""
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise ProviderError(
            f"no adapter registered for provider {name!r}",
            details={"available": [p.value for p in _REGISTRY]},
        ) from exc
    return cls(context)
