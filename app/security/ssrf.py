"""SSRF protection for outbound requests.

Whenever the platform makes an HTTP request to a URL that could be influenced by
a user (customer-supplied webhook endpoints, custom provider base URLs), it must
guard against Server-Side Request Forgery: attempts to make the server reach
internal/metadata/loopback addresses.

:func:`validate_public_url` enforces scheme/port allow-lists and resolves the
host, rejecting any URL that maps to a private, loopback, link-local, reserved,
or otherwise non-public IP address. All resolved addresses are checked, not just
the first, to defeat DNS round-robin bypasses.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import ValidationError

_ALLOWED_SCHEMES = frozenset({"https"})
# http permitted only for loopback in explicit test/sandbox contexts.
_ALLOWED_SCHEMES_WITH_HTTP = frozenset({"http", "https"})
_ALLOWED_PORTS = frozenset({80, 443})


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    host: str
    port: int
    ip_addresses: tuple[str, ...]


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve(host: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationError(f"could not resolve host {host!r}") from exc
    return tuple({str(info[4][0]) for info in infos})


def validate_public_url(url: str, *, allow_http: bool = False) -> ValidatedTarget:
    """Validate that ``url`` is safe to request. Raises :class:`ValidationError`.

    Args:
        allow_http: permit plain ``http`` (only used for sandbox/loopback).
    """
    parts = urlsplit(url)
    schemes = _ALLOWED_SCHEMES_WITH_HTTP if allow_http else _ALLOWED_SCHEMES
    if parts.scheme not in schemes:
        raise ValidationError(
            f"URL scheme {parts.scheme!r} is not allowed",
            details={"allowed": sorted(schemes)},
        )
    if not parts.hostname:
        raise ValidationError("URL is missing a host")

    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in _ALLOWED_PORTS:
        raise ValidationError(
            f"port {port} is not allowed", details={"allowed": sorted(_ALLOWED_PORTS)}
        )

    # An IP literal must itself be public; a hostname must resolve only to public IPs.
    try:
        literal = ipaddress.ip_address(parts.hostname)
    except ValueError:
        literal = None

    if literal is not None:
        addresses: tuple[str, ...] = (str(literal),)
    else:
        addresses = _resolve(parts.hostname)

    if not addresses:
        raise ValidationError(f"host {parts.hostname!r} did not resolve to any address")

    for ip in addresses:
        if not _is_public_ip(ip):
            raise ValidationError(
                "URL resolves to a non-public address and is blocked (SSRF protection)",
                details={"host": parts.hostname, "resolved": list(addresses)},
            )

    return ValidatedTarget(url=url, host=parts.hostname, port=port, ip_addresses=addresses)
