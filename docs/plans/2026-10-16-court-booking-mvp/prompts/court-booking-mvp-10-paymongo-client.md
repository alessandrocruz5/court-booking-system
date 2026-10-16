---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 10
unit: CBS-5
status: todo
model: opus
effort: high
depends_on: [09]
parallel_group: J
files:
  create:
    - apps/backend/payments/__init__.py
    - apps/backend/payments/apps.py
    - apps/backend/payments/env.py
    - apps/backend/payments/paymongo.py
    - apps/backend/payments/webhook.py
    - apps/backend/payments/tests/__init__.py
    - apps/backend/payments/tests/test_env.py
    - apps/backend/payments/tests/test_paymongo.py
    - apps/backend/payments/tests/test_webhook_signature.py
  modify:
    - apps/backend/pyproject.toml
    - apps/backend/uv.lock
    - apps/backend/config/settings.py
    - apps/backend/.env.example
  delete: []
---
# 10 · PayMongo client and webhook signature

## Task
Port fun-run's proven TypeScript PayMongo package to Python as the `payments` Django app. It needs test-key-only env
validation, a Hosted Checkout client (create, retrieve, expire), and webhook signature verification and parsing. Use
the same semantics and the same safety properties. Tests use `httpx.MockTransport`, with no network.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv,
  ruff, pytest against Postgres at `localhost:54329`).
- **Source to port, read only** (keep every behaviour and the doc comments' intent):
  - `/Users/alessandrocruz/Code/fun-run-website/packages/payments/src/env.ts`
  - `/Users/alessandrocruz/Code/fun-run-website/packages/payments/src/checkout.ts`
  - `/Users/alessandrocruz/Code/fun-run-website/packages/payments/src/webhook.ts`
  - `/Users/alessandrocruz/Code/fun-run-website/packages/payments/src/__tests__/*.test.ts`: port the cases.
- `uv add "httpx>=0.28"`, for timeouts and a mockable transport. Add `"payments"` to `INSTALLED_APPS`.
- `apps/backend/.env.example`: add `PAYMONGO_SECRET_KEY=` (the test secret key, `sk_test_…` only, server only) and
  `PAYMONGO_WEBHOOK_SECRET=` (the webhook's signing secret), commented in the file's existing style, with empty values.
- **`payments/env.py`**:
  - `TEST_SECRET_KEY = re.compile(r"^sk_test_[A-Za-z0-9]+$")` and `WEBHOOK_SECRET = re.compile(r"^(?![sp]k_)\S+$")`.
  - `class PaymentsConfigError(Exception)` with `.key`, the env var name. The message names the key and **never the value**.
  - `def get_secret_key(environ=os.environ) -> str` reads `PAYMONGO_SECRET_KEY`, and
    `def get_webhook_secret(environ=os.environ) -> str` reads `PAYMONGO_WEBHOOK_SECRET`. They're read per call, never
    at import (the build reads no env).
- **`payments/paymongo.py`**:
  - `API_URL = "https://api.paymongo.com/v1"`, `TIMEOUT_SECONDS = 10.0`, and
    `PAYMENT_METHOD_TYPES = ("card", "gcash", "paymaya", "grab_pay")` (proven on this PayMongo account in fun-run).
  - `CHECKOUT_SESSION_ID = re.compile(r"^cs_[A-Za-z0-9]+$")` and `def is_checkout_session_id(value: object) -> bool`.
  - `class PayMongoError(Exception)` with `status: int = 0` and `codes: tuple[str, ...] = ()`. It carries the HTTP
    status and PayMongo error `code`s **only**, never a request or response body or a `detail`.
  - `@dataclass(frozen=True) Payment(id, status, amount_centavos, currency, fee_centavos, net_centavos, method,
    paid_at: datetime | None, livemode: bool)` and `CheckoutSession(id, checkout_url, status, livemode,
    metadata: dict[str, str], payments: tuple[Payment, ...])`.
  - `def parse_checkout_session(resource: object) -> CheckoutSession` validates the shape the same way
    `checkoutSessionResource` does (`id` matches `cs_…`; `attributes.checkout_url/status/livemode/metadata/payments`; each payment's
    `attributes.status/amount/currency/fee/net_amount/livemode/paid_at/source.type`). It raises `PayMongoError`
    ("Unexpected PayMongo checkout session") on any mismatch. `paid_at` comes from unix seconds as an aware UTC
    datetime, and the method is `source.type` or `"unknown"`.
  - `class PayMongoClient`:
    - `__init__(self, secret_key: str, *, transport: httpx.BaseTransport | None = None)` raises `ValueError` unless
      the key matches `TEST_SECRET_KEY`, whatever the environment says. Auth is HTTP Basic with the key as the username
      and an empty password.
    - `create_checkout_session(self, *, booking_id: str, line_item_name: str, amount_centavos: int, description: str,
      success_url: str, cancel_url: str) -> CheckoutSession`. The amount must be a positive int, or it raises
      `ValueError`. It POSTs `/checkout_sessions` with `line_items=[{name, amount, currency:"PHP", quantity:1}]`,
      `payment_method_types`, `description`, the success and cancel URLs, `send_email_receipt: false`,
      `show_description: true`, `show_line_items: true`, and **`metadata: {"booking_id": booking_id}` only**. It
      refuses a returned `checkout_url` whose scheme isn't `https` or whose host isn't `checkout.paymongo.com`.
    - `retrieve_checkout_session(self, session_id) -> CheckoutSession` validates the ID first (`ValueError`) and raises
      if PayMongo returns a different ID.
    - `expire_checkout_session(self, session_id) -> CheckoutSession` validates the ID, then POSTs
      `/checkout_sessions/{id}/expire` with no body. Documented in PayMongo's API reference as "Expire a Checkout
      Session", it cancels the attached payment intent.
    - A transport failure or timeout raises `PayMongoError("PayMongo request failed")`. A non-2xx response raises
      `PayMongoError(f"PayMongo responded {status}", status, codes)`. An unexpected JSON shape raises
      `PayMongoError("Unexpected PayMongo response", status)`.
  - `def get_client() -> PayMongoClient` builds one per call from `get_secret_key()`.
- **`payments/webhook.py`**:
  - `SIGNATURE_HEADER = "Paymongo-Signature"`, `SIGNATURE_META_KEY = "HTTP_PAYMONGO_SIGNATURE"`,
    `SIGNATURE_TOLERANCE_SECONDS = 300` and `CHECKOUT_SESSION_PAID = "checkout_session.payment.paid"`.
  - `@dataclass(frozen=True) SignatureCheck(ok: bool, reason: str | None)`, where reason is one of
    `missing | malformed | stale | mismatch`.
  - `def verify_signature(*, header: str | None, raw_body: bytes, secret: str, now: int | None = None) -> SignatureCheck`.
    Parse `t=…,te=…,li=…`. A part with no `=`, an empty key or a repeated key is malformed, and empty parts are
    skipped. `t` must match `^\d{1,12}$` and `te` must match `^[0-9a-fA-F]{64}$`. Allow ±300 s. The HMAC-SHA256
    covers `f"{t}.".encode() + raw_body`, keyed with the secret. Compare with `hmac.compare_digest`. **Only `te` is
    checked** (test mode), so a live delivery never verifies.
  - `@dataclass(frozen=True) WebhookEvent(id, type, livemode, data: object)` and
    `def parse_event(raw_body: bytes) -> WebhookEvent`. It raises `PayMongoError("PayMongo event is not JSON")` or
    `("Unexpected PayMongo event")`, and never quotes the body.
- **Tests**:
  - `test_env.py`: an `sk_live_…` key, a `pk_test_…` key, `""` and whitespace are all refused, and the error message
    doesn't contain the value. A webhook secret that starts with `sk_` or `pk_` is refused.
  - `test_paymongo.py`:
    - The client refuses a live key.
    - The create request carries Basic auth with the key, `metadata == {"booking_id": …}` exactly, and the method list.
    - A non-PayMongo `checkout_url` raises.
    - A 400 with `{"errors":[{"code":"parameter_invalid","detail":"secret stuff"}]}` raises with codes
      `("parameter_invalid",)`, and the message doesn't contain "secret stuff".
    - A timeout raises `PayMongoError`.
    - Retrieve validates the ID and refuses another session.
    - Expire POSTs to `/expire`.
    - `parse_checkout_session` maps a paid payment.
  - `test_webhook_signature.py`: valid; missing; malformed (no `te`, bad hex, duplicate key); stale at ±301 s; mismatch
    (body changed by one byte); a live-only signature with `te` empty is refused; `parse_event` handles non-JSON and
    the wrong shape. Build the signatures in the tests with `hmac`.
- Review constraints: **test mode only**, **personal data** (metadata carries the booking ID only, and no bodies in
  errors or logs), and **secrets read per call**.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add views, URLs or booking-state changes. Prompt 11 does that.
- Use the `requests` library or a PayMongo SDK. Use httpx only.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest payments -q
```
