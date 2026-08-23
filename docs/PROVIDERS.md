# Provider integration guide

A provider is any payment backend (Stripe, PayPal, a crypto processor, an
in-house gateway). UPGI talks to all of them through **one interface**, so the
rest of the system is provider-agnostic.

## The interface

Implement `app/providers/base.py::BasePaymentProvider`:

```python
class BasePaymentProvider(ABC):
    name: ProviderName

    async def create_payment(self, request: ChargeRequest) -> ProviderCharge: ...
    async def capture(self, reference: str, amount: Money) -> ProviderCharge: ...
    async def cancel(self, reference: str) -> ProviderCharge: ...
    async def refund(self, reference: str, amount: Money, reason=None) -> ProviderRefund: ...
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhook: ...
```

Adapters receive a `ProviderContext` (decrypted `secret`, `sandbox` flag,
non-secret `config`, and an injected async `http` client). They translate the
unified DTOs to the provider's native API and normalise the response — mapping
the provider's statuses to `PaymentStatus`.

## Adding a provider in three steps

1. **Create the adapter** in `app/providers/acme.py`:

   ```python
   from app.providers.base import BasePaymentProvider, ProviderCharge
   from app.providers.registry import register_provider
   from app.domain.enums import ProviderName

   @register_provider(ProviderName.ACME)
   class AcmeProvider(BasePaymentProvider):
       async def create_payment(self, request):
           resp = await self.context.http.post("/charges", json={...})
           ...
   ```

2. **Register the enum** member in `app/domain/enums.py` (`ACME = "acme"`).

3. **Import it** in `app/providers/__init__.py` so the decorator runs.

No existing business logic changes. The Gateway Manager will resolve, decrypt
credentials for, and wrap your adapter in resilience automatically.

## Credentials

Store per-tenant credentials via `ProviderConfig`. The secret is encrypted at
rest with AES-256-GCM (bound to the owner via AAD). The Gateway Manager decrypts
it just-in-time and passes it to the adapter through `ProviderContext.secret` —
adapters must never log it.

## Sandbox & testing

- The bundled **mock** provider is deterministic and offline. Use it for local
  development, demos, and CI. Magic inputs (`payment_method_token="pm_fail"` or
  `metadata.force_failure=true`) force declines; it also signs webhooks so it
  doubles as a webhook simulator.
- Test real adapters by injecting an `httpx.AsyncClient` backed by a
  `MockTransport` (see `tests/test_provider_stripe.py`) — full request/response
  logic is exercised with zero network access.

## Webhooks

If the provider signs webhooks with the `t=…,v1=HMAC-SHA256` scheme, reuse
`app/security/signatures.py` directly (as the Stripe adapter does). Otherwise,
implement the provider's scheme inside `verify_webhook`; the engine handles
deduplication and persistence once you return a `ProviderWebhook`.
