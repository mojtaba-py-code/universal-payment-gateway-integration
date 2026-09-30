# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project adheres to
Semantic Versioning.

## [Unreleased]

### Security
- Require PyJWT >= 2.14.0. PyJWT 2.13.0 has ten published advisories, among them
  algorithm confusion and acceptance of malformed signature segments; a
  range that still allowed it could resolve to it.

### Fixed
- Depend on `SQLAlchemy[asyncio]` rather than bare `SQLAlchemy`. SQLAlchemy 2.1
  no longer installs `greenlet` by default, so a fresh install resolved 2.1 without
  it and the async engine raised `ImportError` on first use.

### Changed
- The weekly CI run moved from 06:00 to 06:17 UTC on Mondays. GitHub can delay or
  drop scheduled runs at the top of the hour under load.

## [1.0.0] - 2026-08-06

### Added
- Provider-agnostic payment core with an adapter interface, plugin registry, and
  factory. Bundled **mock/sandbox** and **Stripe** adapters.
- Full payment lifecycle: create, authorize, capture (full/partial), cancel, and
  refund (full/partial), guarded by an explicit state machine.
- Authentication & authorization: registration, login, JWT access/refresh tokens,
  API keys (hash-at-rest), and role/scope-based access control.
- Idempotency for unsafe operations via the `Idempotency-Key` header.
- Webhook engine: HMAC signature verification, replay protection, and idempotent
  (deduplicated) processing with persisted events.
- Security: Argon2id passwords, AES-256-GCM envelope encryption for provider
  secrets (with key rotation), SSRF protection, rate limiting, security headers,
  and log redaction.
- Resilience: retry with jittered backoff and a per-provider circuit breaker.
- Observability: structured JSON logging with correlation ids, Prometheus
  metrics, and health/readiness probes.
- Tooling: Docker multi-stage build, docker-compose stack (API + PostgreSQL +
  Redis + NGINX), Alembic migrations, GitHub Actions CI, and a Pytest suite.
