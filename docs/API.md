# API guide

Base URL: `/api/v1`. Interactive docs: `/docs` (Swagger) and `/redoc`.
OpenAPI schema: `/openapi.json`.

## Authentication

Two mechanisms, both accepted on protected endpoints:

- **Bearer JWT** — `Authorization: Bearer <access_token>` from `/auth/login`.
- **API key** — `X-API-Key: upgi_sk_...` from `/auth/api-keys`.

## Conventions

- **Money** is always integer **minor units** + ISO-4217 currency. `4999 USD`
  means $49.99. Responses also include a `display` string.
- **Idempotency**: send `Idempotency-Key: <unique>` on `POST /payments` and
  `POST /payments/{id}/refunds`. Re-sending the same key + body returns the
  original response; a different body returns `409 idempotency_conflict`.
- **Correlation**: every response includes `X-Correlation-ID`; send your own to
  trace a request across logs.
- **Pagination**: list endpoints accept `limit` and `offset` and return
  `{items, meta:{total, limit, offset}}`.

## Error envelope

All errors share one shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "request validation failed",
    "details": { "errors": [ ... ] },
    "correlation_id": "…"
  }
}
```

Stable codes: `validation_error`, `authentication_failed`, `permission_denied`,
`not_found`, `conflict`, `idempotency_conflict`, `rate_limited`, `invalid_state`,
`provider_error`, `provider_unavailable`, `circuit_open`, `signature_invalid`,
`replay_detected`, `unsupported_currency`, `internal_error`.

## Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Obtain access + refresh tokens |
| POST | `/auth/refresh` | Exchange a refresh token |
| GET | `/auth/me` | Current user |
| POST | `/auth/api-keys` | Create an API key (returned once) |
| GET | `/auth/api-keys` | List API keys |
| DELETE | `/auth/api-keys/{id}` | Revoke an API key |

### Payments
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/payments` | `payments:write` | Create a payment |
| GET | `/payments` | `payments:read` | List (filter `?status=`) |
| GET | `/payments/{id}` | `payments:read` | Retrieve |
| POST | `/payments/{id}/capture` | `payments:write` | Capture an authorized payment |
| POST | `/payments/{id}/cancel` | `payments:write` | Cancel/void |
| POST | `/payments/{id}/refunds` | `refunds:write` | Refund (full/partial) |

### Webhooks & admin
| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/{provider}` | Receive a signed provider webhook |
| GET | `/admin/providers` | Registered providers & currencies (admin) |
| GET | `/admin/stats` | Aggregate payment statistics (admin) |

### Ops
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness (checks DB) |
| GET | `/metrics` | Prometheus metrics |

## Example: manual authorize then capture

```bash
# Authorize only (capture_method=manual)
PID=$(curl -s localhost:8000/api/v1/payments -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"amount_minor":10000,"currency":"USD","capture_method":"manual"}' | jq -r .id)

# Capture later (optionally a partial amount)
curl -s localhost:8000/api/v1/payments/$PID/capture -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"amount_minor":10000}'
```
