# Architecture

UPGI follows a **clean, layered architecture**. Dependencies point inward:
the domain and service layers never import the web framework or a provider SDK.
This keeps business rules testable in isolation and lets the outer layers
(HTTP, database, provider transport) change without rippling inward.

## Layers

| Layer | Package | Responsibility | Depends on |
|-------|---------|----------------|-----------|
| API | `app/api` | HTTP routing, request/response validation, DI wiring, error mapping | services, schemas |
| Schemas | `app/schemas` | Pydantic contracts (the public API surface) | domain |
| Services | `app/services` | Orchestration & business rules | repositories, domain, providers (via manager) |
| Gateway Manager | `app/services/gateway_manager.py` | Facade over providers + resilience | providers, security |
| Providers | `app/providers` | Adapters translating the unified interface to a gateway | domain, security |
| Repositories | `app/repositories` | Persistence (only layer touching the ORM) | db |
| Domain | `app/domain` | Enums, RBAC scopes, payment state machine | core |
| Core | `app/core` | Config, logging, money, errors, resilience, metrics | — |
| Security | `app/security` | Passwords, JWT, API keys, crypto, SSRF, signatures | core |

## Request flow (create payment)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant MW as Middleware
    participant EP as Payments router
    participant IS as Idempotency
    participant PS as PaymentService
    participant GM as GatewayManager
    participant PR as Provider adapter
    participant DB as Database

    C->>MW: POST /api/v1/payments (+ Idempotency-Key)
    MW->>EP: correlation id, rate limit, auth
    EP->>IS: lookup(owner, key, body)
    alt cached
        IS-->>C: stored response
    else first time
        EP->>PS: create_payment(...)
        PS->>DB: insert payment (requires_confirmation)
        PS->>GM: execute(provider, create)
        GM->>PR: create_payment (retry + circuit breaker)
        PR-->>GM: ProviderCharge(status)
        GM-->>PS: result
        PS->>DB: update status (state machine), audit
        PS-->>EP: payment
        EP->>IS: store(response)
        EP-->>C: 201 payment
    end
```

## Payment state machine

```mermaid
stateDiagram-v2
    [*] --> requires_confirmation
    requires_confirmation --> authorized
    requires_confirmation --> captured
    requires_confirmation --> canceled
    requires_confirmation --> failed
    authorized --> captured
    authorized --> canceled
    authorized --> failed
    captured --> partially_refunded
    captured --> refunded
    partially_refunded --> partially_refunded
    partially_refunded --> refunded
    refunded --> [*]
    canceled --> [*]
    failed --> [*]
```

Transitions are centralised in `app/domain/state_machine.py`; the service layer
calls `assert_transition` before persisting, so illegal jumps are impossible.

## Data model (ER)

```mermaid
erDiagram
    USERS ||--o{ API_KEYS : owns
    USERS ||--o{ PAYMENTS : owns
    USERS ||--o{ PROVIDER_CONFIGS : configures
    USERS ||--o{ IDEMPOTENCY_KEYS : scopes
    USERS ||--o{ AUDIT_LOGS : actor
    PAYMENTS ||--o{ REFUNDS : has
    USERS {
        uuid id PK
        string email
        string hashed_password
        enum role
    }
    PAYMENTS {
        uuid id PK
        enum provider
        string provider_reference
        bigint amount
        string currency
        bigint amount_captured
        bigint amount_refunded
        enum status
    }
    REFUNDS {
        uuid id PK
        uuid payment_id FK
        bigint amount
        enum status
    }
    WEBHOOK_EVENTS {
        uuid id PK
        enum provider
        string event_id
        enum status
    }
```

## Resilience

Every outbound provider call is wrapped by the Gateway Manager:

- **Retry** — exponential backoff with full jitter, only for transient
  (infrastructure) failures.
- **Circuit breaker** — per provider; opens after N consecutive infra failures
  and fails fast until a cool-off elapses. **Business declines never trip it**,
  so a wave of legitimately declined cards does not take a provider offline.

## Extensibility

The provider **registry + factory** (`app/providers/registry.py`) is a plugin
seam: an adapter registers itself with a decorator and becomes resolvable by
name. The system is **open for extension, closed for modification** — new
providers, currencies, and payment methods are additive.
