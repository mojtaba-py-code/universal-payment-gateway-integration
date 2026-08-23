# Security model

Security is a first-class concern in UPGI. This document describes the controls
and maps them to the OWASP Top 10 and PCI-DSS-aligned best practices.

> **Scope note.** UPGI is an orchestration layer. It never stores raw card data
> (PAN/CVV); it works with provider-issued **payment method tokens**, keeping the
> cardholder data environment with the providers and drastically reducing PCI
> scope.

## Authentication & authorization

- **Passwords**: Argon2id (`argon2-cffi`) with tuned parameters. Hashes are
  transparently upgraded on login when parameters strengthen. Verification is
  constant-time, and login runs a dummy verification for unknown users to avoid
  timing-based user enumeration.
- **JWT**: HS256 access/refresh tokens carrying `iss`, `aud`, `exp`, `iat`,
  `nbf`, `jti`, and a `type` claim. A refresh token can never be replayed as an
  access token.
- **API keys**: generated with a CSPRNG; only a SHA-256 hash is stored (indexed).
  Keys are shown once. Verification is constant-time.
- **RBAC**: roles map to fine-grained scopes (`app/domain/rbac.py`); endpoints
  require explicit scopes.
- **Brute force**: failed-login counter with lockout threshold.

## Secrets at rest

Provider credentials are encrypted with **AES-256-GCM** envelope encryption
(`app/security/crypto.py`):

- Random 96-bit nonce per encryption; authenticated (tamper-evident).
- **Additional Authenticated Data (AAD)** binds ciphertext to its owner, so a
  ciphertext cannot be moved between records.
- **Key rotation**: ciphertexts are tagged with a key id; multiple keys can be
  held so old data stays readable while new data uses the current key.

## Webhooks

- **Signature verification**: HMAC-SHA256 over `"{timestamp}.{body}"`
  (Stripe-compatible), constant-time comparison.
- **Replay protection**: signed timestamp must fall inside a tolerance window.
- **Idempotency**: a unique `(provider, event_id)` constraint plus an explicit
  lookup guarantee each event is processed at most once.
- Verification happens on the **raw** body before any parsing or persistence, so
  forged/stale deliveries leave no state behind.

## Outbound requests (SSRF)

`app/security/ssrf.py` validates any user-influenced outbound URL: scheme and
port allow-lists, and DNS resolution with rejection of private, loopback,
link-local, reserved, and cloud-metadata addresses (checking **all** resolved
IPs to defeat round-robin bypasses).

## Transport & input hardening

- Rate limiting per identity (API key / bearer / IP) with `Retry-After`.
- Strict security headers (CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) — set by the app and reinforced by NGINX.
- CORS allow-list (wildcards rejected in production).
- Pydantic validates and coerces every request; responses are typed.
- Money is integer minor units — never floating point.
- Idempotency keys prevent duplicate charges on retries.

## Logging

Structured JSON logs carry a correlation id per request. A redaction processor
strips sensitive keys (passwords, tokens, secrets, card fields) so they can
never reach the log sink even if passed by mistake.

## Fail-safe configuration

On startup in `production`, the app refuses to boot with insecure defaults
(default JWT secret, default encryption key, debug on, or wildcard CORS) — see
`Settings.assert_production_ready`.

## OWASP Top 10 mapping

| Risk | Mitigation |
|------|-----------|
| A01 Broken Access Control | Scope-based RBAC; owner-scoped queries; per-request auth |
| A02 Cryptographic Failures | Argon2id; AES-256-GCM; TLS/HSTS; no secrets in logs |
| A03 Injection | SQLAlchemy parameterised queries; strict validation |
| A04 Insecure Design | State machine, idempotency, circuit breaker, fail-safe config |
| A05 Security Misconfiguration | Prod secret checks; security headers; least-privilege container |
| A07 Auth Failures | Token typing, lockout, constant-time checks |
| A08 Data Integrity | Signed & replay-protected webhooks; audit log |
| A09 Logging Failures | Structured logs, correlation ids, audit trail |
| A10 SSRF | Dedicated outbound URL validation |

## Reporting

Please report vulnerabilities privately to the maintainer rather than opening a
public issue.
