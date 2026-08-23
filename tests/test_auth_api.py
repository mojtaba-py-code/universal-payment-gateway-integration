"""End-to-end tests for the auth, user, and API-key endpoints."""

from __future__ import annotations

import httpx

_PREFIX = "/api/v1/auth"


async def _register(
    client: httpx.AsyncClient, email: str = "merchant@example.com"
) -> httpx.Response:
    return await client.post(
        f"{_PREFIX}/register",
        json={"email": email, "password": "correct horse battery", "full_name": "Merchant"},
    )


async def test_register_login_me_flow(client: httpx.AsyncClient) -> None:
    reg = await _register(client)
    assert reg.status_code == 201
    assert reg.json()["email"] == "merchant@example.com"
    assert reg.json()["role"] == "merchant"

    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "merchant@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        f"{_PREFIX}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "merchant@example.com"


async def test_duplicate_registration_conflicts(client: httpx.AsyncClient) -> None:
    await _register(client, "dup@example.com")
    again = await _register(client, "dup@example.com")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "conflict"


async def test_weak_password_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        f"{_PREFIX}/register", json={"email": "weak@example.com", "password": "short"}
    )
    assert resp.status_code == 422


async def test_login_wrong_password(client: httpx.AsyncClient) -> None:
    await _register(client, "wrong@example.com")
    resp = await client.post(
        f"{_PREFIX}/login", json={"email": "wrong@example.com", "password": "nope-nope-nope"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_failed"


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"{_PREFIX}/me")
    assert resp.status_code == 401


async def test_refresh_token_flow(client: httpx.AsyncClient) -> None:
    await _register(client, "refresh@example.com")
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "refresh@example.com", "password": "correct horse battery"},
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_api_key_lifecycle(client: httpx.AsyncClient) -> None:
    await _register(client, "keys@example.com")
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "keys@example.com", "password": "correct horse battery"},
    )
    bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = await client.post(f"{_PREFIX}/api-keys", json={"name": "server"}, headers=bearer)
    assert created.status_code == 201
    full_key = created.json()["api_key"]
    key_id = created.json()["id"]
    assert full_key.startswith("upgi_sk_")

    # The API key authenticates just like a bearer token.
    me_via_key = await client.get(f"{_PREFIX}/me", headers={"X-API-Key": full_key})
    assert me_via_key.status_code == 200

    listed = await client.get(f"{_PREFIX}/api-keys", headers=bearer)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    revoked = await client.delete(f"{_PREFIX}/api-keys/{key_id}", headers=bearer)
    assert revoked.status_code == 204

    # Revoked key no longer authenticates.
    after = await client.get(f"{_PREFIX}/me", headers={"X-API-Key": full_key})
    assert after.status_code == 401
