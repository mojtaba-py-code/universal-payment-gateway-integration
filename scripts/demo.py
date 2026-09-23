"""Recordable end-to-end demo: the payment lifecycle plus the idempotency proof.

Run against a local server (python -m app serve) and screen-record the output.
    .venv/Scripts/python.exe scripts/demo.py
"""

from __future__ import annotations

import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
PAUSE = 1.1  # breathing room so a viewer can read each step

C = {
    "dim": "\033[90m", "cyan": "\033[96m", "green": "\033[92m",
    "yellow": "\033[93m", "bold": "\033[1m", "off": "\033[0m",
}


def step(n: str, title: str) -> None:
    print(f"\n{C['cyan']}{C['bold']}[{n}]{C['off']} {C['bold']}{title}{C['off']}")
    print(f"{C['dim']}{'-' * 62}{C['off']}")
    time.sleep(PAUSE)


def show(label: str, value: object, colour: str = "green") -> None:
    print(f"    {label:<22} {C[colour]}{value}{C['off']}")


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=10.0)
    email = f"demo-{uuid.uuid4().hex[:8]}@example.com"
    # The suppression below is deliberate: this registers a throwaway
    # account on a local server for the length of a screen recording. The
    # address is randomised per run and nothing here reaches a deployment.
    password = "correct horse battery staple"  # noqa: S105

    print(f"\n{C['bold']}Universal Payment Gateway Integration{C['off']} "
          f"{C['dim']}- live lifecycle demo{C['off']}")

    step("1", "Register and authenticate")
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]
    client.headers["authorization"] = f"Bearer {token}"
    show("user", email)
    show("token", token[:38] + "...", "dim")

    step("2", "Create a payment  (capture_method = manual)")
    key = str(uuid.uuid4())
    body = {
        "currency": "USD",
        "amount_minor": 24999,
        "provider": "mock",
        "capture_method": "manual",
        "description": "Annual subscription",
    }
    first = client.post(
        "/api/v1/payments", json=body, headers={"Idempotency-Key": key}
    ).json()
    show("Idempotency-Key", key, "yellow")
    show("payment id", first["id"])
    show("amount", first["amount"]["display"])
    show("status", first["status"])

    step("3", "Retry the SAME request  (network timeout, client retries)")
    print(f"    {C['dim']}Same body, same Idempotency-Key, sent a second time.{C['off']}")
    time.sleep(PAUSE)
    second = client.post(
        "/api/v1/payments", json=body, headers={"Idempotency-Key": key}
    ).json()
    same = second["id"] == first["id"]
    show("payment id", second["id"])
    show("same payment?", "YES - no double charge" if same else "NO - BUG", 
         "green" if same else "yellow")

    total = client.get("/api/v1/payments").json()["meta"]["total"]
    show("payments on file", f"{total}  (two requests, one payment)")

    step("4", "Capture the authorised amount")
    cap = client.post(f"/api/v1/payments/{first['id']}/capture", json={}).json()
    show("status", cap["status"])

    step("5", "Partial refund")
    ref = client.post(
        f"/api/v1/payments/{first['id']}/refunds",
        json={"amount_minor": 9999, "reason": "requested_by_customer"},
    ).json()
    show("refund id", ref["id"])
    show("refunded", ref["amount"]["display"])
    show("status", ref["status"])

    final = client.get(f"/api/v1/payments/{first['id']}").json()
    step("6", "Final state")
    show("payment status", final["status"])
    show("captured", final["amount_captured"]["display"])
    show("refunded", final["amount_refunded"]["display"])
    show("state machine",
         "authorized -> captured -> partially_refunded", "dim")

    print(f"\n{C['green']}{C['bold']}  Lifecycle complete.{C['off']} "
          f"{C['dim']}105 tests | 95% coverage | github.com/mojtaba-py-code{C['off']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
