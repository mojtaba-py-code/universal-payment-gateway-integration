"""Tests for SSRF protection."""

from __future__ import annotations

import pytest
from app.core.errors import ValidationError
from app.security.ssrf import validate_public_url


def test_public_ip_literal_allowed() -> None:
    target = validate_public_url("https://8.8.8.8/webhook")
    assert target.host == "8.8.8.8"
    assert "8.8.8.8" in target.ip_addresses


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/x",  # loopback
        "https://10.0.0.5/x",  # private
        "https://192.168.1.1/x",  # private
        "https://169.254.169.254/latest/meta-data",  # cloud metadata / link-local
        "https://[::1]/x",  # ipv6 loopback
    ],
)
def test_private_and_metadata_blocked(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_public_url(url)


def test_scheme_enforced() -> None:
    with pytest.raises(ValidationError):
        validate_public_url("http://8.8.8.8/x")  # http not allowed by default
    # http allowed only when explicitly opted in
    validate_public_url("http://8.8.8.8/x", allow_http=True)


def test_port_allowlist() -> None:
    with pytest.raises(ValidationError):
        validate_public_url("https://8.8.8.8:8443/x")


def test_missing_host_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_public_url("https:///nohost")


def test_unresolvable_host_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_public_url("https://nonexistent.invalid.tld.example/x")
