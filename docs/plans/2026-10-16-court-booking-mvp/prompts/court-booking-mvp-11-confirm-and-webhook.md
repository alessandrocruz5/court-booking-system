---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 11
unit: CBS-5
status: done
model: opus
effort: xhigh
depends_on: [10]
parallel_group: K
files:
  create:
    - apps/backend/payments/confirm.py
    - apps/backend/payments/views.py
    - apps/backend/payments/urls.py
    - apps/backend/payments/tests/test_confirm.py
    - apps/backend/payments/tests/test_webhook_view.py
  modify:
    - apps/backend/config/urls.py
    - docs/runbook.md
  delete: []
---
# 11 · Payment confirmation and webhook endpoint

## Task
Implement the single idempotent path by which a booking becomes paid, `confirm_payment()`, plus the success-page
check `check_checkout()` and the cancel-page release `release_checkout()`. Also add the signed PayMongo webhook at
`POST /webhooks/paymongo`. Port fun-run's semantics and add late-payment handling for expired holds.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`).
- **Source to port, read only**:
  - `/Users/alessandrocruz/Code/fun-run-website/apps/web/src/lib/registration/confirm.ts:43-84` (`logError`, which logs
    an error class, status, codes and SQLSTATE but never a message) and `:166-228` (`confirmPayment`, `checkCheckout`).
    Leave out the email parts.
  - `/Users/alessandrocruz/Code/fun-run-website/apps/web/app/api/webhooks/paymongo/route.ts`: the status codes and the
    order of checks.
- Already there (read them):
  - `payments/paymongo.py`: `CheckoutSession`, `Payment`, `PayMongoError`, `get_client()`, `is_checkout_session_id()`,
    `parse_checkout_session()`.
  - `payments/webhook.py`: `verify_signature()`, `parse_event()`, `SIGNATURE_META_KEY`, `CHECKOUT_SESSION_PAID`.
  - `payments/env.py`: `get_webhook_secret()`, `PaymentsConfigError`.
  - `bookings/models.py`: `Booking`, with `status` one of pending/confirmed/expired/cancelled/needs_refund, plus
    `checkout_session_id`, `price_centavos`, `payment_id`, `payment_method`, `fee_centavos`, `net_centavos`, `paid_at`
    and `hold_expires_at`. Also `SlotLock`.
  - `bookings/holds.py`: `reacquire(booking, *, now=None) -> bool` (re-claims the same court, spaces and hours for an
    `expired`, or lapsed `pending`, online booking, without changing status) and
    `release(booking, *, status, now=None) -> bool`. As built in CBS-4: `reacquire` must run inside `atomic()`
    (`RuntimeError` otherwise); it re-locks the row with `select_for_update` and judges that copy (`ValueError` for a
    non-online booking or one that isn't `expired`/`pending`, so route `cancelled` to `needs_refund` without calling it);
    it returns **False once `starts_at <= now`**, so a payment that lands after the slot started becomes `needs_refund`
    (test it). "Hold expired but slots still free → confirmed" fixtures need a slot that hasn't started at the `now`
    they pass. `release(status="expired")` is allowed only from `pending` (`ValueError` from `confirmed`); an
    already-final booking returns False first.
- **`payments/confirm.py`**:
  - `@dataclass(frozen=True) ConfirmResult(status: str, booking: Booking | None = None, reason: str | None = None)`.
    The status is `confirmed | pending | needs_refund | rejected`, and the reject reasons are `livemode`,
    `unknown_session`, `metadata_mismatch`, `amount_mismatch` and `not_recorded`.
  - `def log_error(event: str, error: BaseException, **ids: str) -> None`. Log the class name, `PayMongoError`
    status and codes, `PaymentsConfigError.key`, or a psycopg SQLSTATE. **Never `str(error)`**, because DB errors
    quote parameters (names, emails). Use logger `cb.payments`.
  - `def confirm_payment(session: CheckoutSession, *, now=None) -> ConfirmResult`:
    1. Reject `session.livemode`.
    2. Look up the booking by `checkout_session_id`. If there's none, reject `unknown_session`.
       `session.metadata.get("booking_id") != str(booking.id)` rejects `metadata_mismatch`.
    3. Already `confirmed` → return `confirmed`. Already `needs_refund` → return `needs_refund`. Both are idempotent.
    4. Find the paid payment: `status == "paid"`. If there's none, return `pending`. A `livemode` payment is rejected.
       `currency != "PHP"` or `amount_centavos != booking.price_centavos` rejects `amount_mismatch`.
    5. In `transaction.atomic()`, `select_for_update()` the booking and re-check its status (another caller may have won).
       - `pending` with its locks present: mark it confirmed.
       - `expired`, or `pending` with no locks: call `reacquire()`. True → mark it confirmed. False → set status
         `needs_refund` and record the payment fields anyway, so staff can refund it. Log `payment.needs_refund` with
         the reference.
       - `cancelled` → `needs_refund` as well (paid after the hold was released).
       - "Mark confirmed" means: `status=confirmed`, `hold_expires_at=None`, and set `payment_id`, `payment_method`,
         `fee_centavos`, `net_centavos` and `paid_at` (or `now`).
    6. Return the result. A caller that loses a race sees the winner's state on its re-check, so only one write wins.
  - `def check_checkout(checkout_session_id: str | None) -> CheckResult`. The status is
    `confirmed | pending | needs_refund | not_found | unavailable`, with the booking.
    - An invalid ID or an unknown booking → `not_found`. **Never send an ID we don't know to PayMongo.**
    - An already final status → return it without calling PayMongo.
    - Otherwise retrieve the session and call `confirm_payment`.
    - `rejected` → `not_found`. Any exception → `log_error(...)`, then `unavailable`.
  - `def release_checkout(checkout_session_id: str | None) -> str` returns `released | already_paid | not_found`.
    - For a `pending` booking: first `release(booking, status="cancelled")`, then, **after that commits**,
      best-effort `get_client().expire_checkout_session(id)`. Log a failure; the booking is released anyway.
    - `confirmed` or `needs_refund` → `already_paid`. `expired` or `cancelled` → `released`.
- **`payments/views.py`**, `paymongo_webhook`, decorated `@csrf_exempt` and `@require_POST`:
  1. `get_webhook_secret()`. A `PaymentsConfigError` → log, then 500 `{"error":"unavailable"}`.
  2. `raw = request.body`, then `verify_signature(header=request.META.get(SIGNATURE_META_KEY), raw_body=raw, secret=…)`.
     If it fails → log `webhook.unauthorized reason=…`, then **401 `{"error":"invalid_signature"}` before any DB access**.
  3. `parse_event(raw)`. On error → 400 `{"error":"invalid_event"}`. `event.livemode` → 400 `{"error":"livemode"}`.
  4. Any other `event.type` → 200 `{"outcome":"ignored"}`.
  5. `parse_checkout_session(event.data)`. On error → 400.
  6. `confirm_payment(session)`. Answer 200 `{"outcome": result.status}`. `rejected` also gets 200, since a retry
     can't fix it. An unexpected exception → `log_error`, then 500 so PayMongo retries.
  - Every response is JSON with `Cache-Control: no-store`.
- `payments/urls.py` has `path("paymongo", views.paymongo_webhook)`. In `config/urls.py`, add
  `path("webhooks/", include("payments.urls"))`.
- **`docs/runbook.md`**: append `## PayMongo (test mode)`. The owner follows it when this unit merges:
  - In the PayMongo dashboard, in **test mode**, copy the test secret key (`sk_test_…`) into the
    `cb-paymongo-secret-key` secret, replacing the placeholder. Never a live key; the code refuses one anyway.
  - Register the webhook once per environment through the API, with basic auth on the test secret key:
    `curl -s -u "$PAYMONGO_SECRET_KEY:" https://api.paymongo.com/v1/webhooks -H 'content-type: application/json'
    -d '{"data":{"attributes":{"url":"'"$BACKEND_URL"'/webhooks/paymongo","events":["checkout_session.payment.paid"]}}}'`.
    Store the response's `data.attributes.secret_key` in `cb-paymongo-webhook-secret`, and don't paste the response
    anywhere else.
  - Disable the old version of each secret so 6 stay active, then redeploy (Actions → Deploy → Run workflow).
  - Local testing: put both values in `apps/backend/.env`. Webhooks can't reach localhost, so locally the success
    page's server-side check confirms the booking.
  - A `needs_refund` booking is refunded by hand in the PayMongo test dashboard. It stays flagged on the dashboard as
    an audit trail; nothing in the app clears it.
- **Tests**:
  - `test_confirm.py`. Build bookings with `bookings.holds.create_hold` and set `checkout_session_id`.
    - Paid → confirmed, with the payment fields set.
    - Calling it twice → one write (assert `updated_at` doesn't change on the second call), and still `confirmed`.
    - Amount mismatch, metadata mismatch, livemode and unknown session are rejected.
    - No paid payment → `pending`.
    - Hold expired but slots still free → confirmed, with locks re-created.
    - Hold expired and the slot taken by another booking → `needs_refund`, with no locks for it.
    - **Race**: 2 threads confirm the same session under
      `django_db(transaction=True, serialized_rollback=True)` (it needs the seeded courts), and both see `confirmed`
      with exactly one write.
    - `check_checkout`: an unknown ID → `not_found` and the client is never called (mock `get_client` and assert
      it's uncalled); a PayMongo error → `unavailable`.
    - `release_checkout`: pending → released, the locks are gone, and expire was called. Confirmed → `already_paid`.
  - `test_webhook_view.py`: sign the payloads in the test with a secret set through `monkeypatch.setenv`.
    - No signature → 401 with **zero DB queries** (`django_assert_num_queries(0)`).
    - Bad signature → 401. Stale → 401.
    - Livemode → 400. Another event type → 200 ignored.
    - A paid event → 200 `confirmed`, and the booking is confirmed.
    - The same event twice → both 200.
    - The secret is missing → 500.
    - GET → 405.
    - Every response has `no-store`.
- Review constraints: **payment status comes only from the server** (the signed webhook or a server-side lookup, one
  idempotent `confirm_payment()`); **test mode only**; **no external HTTP inside a DB transaction**; **personal data
  stays out of logs**.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Trust any value from a URL or query string. Nothing here reads one.
- Add the storefront API or any email sending.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
grep -n '## PayMongo (test mode)' docs/runbook.md
cd apps/backend && uv run pytest payments bookings -q
```
