---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 03
unit: CBS-13
status: todo
model: opus
effort: high
depends_on: [02]
parallel_group: B
files:
  create: []
  modify:
    - apps/backend/payments/confirm.py
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/tests/test_schedule.py
    - apps/backend/storefront/views.py
    - apps/backend/storefront/tests/test_bookings_api.py
  delete: []
---
# 03 · One checkout-session expiry; expire orphaned sessions

## Task
1. Make `payments.confirm._expire_session` public as `expire_session`, and use it from the dashboard's cancel instead
   of the duplicate `dashboard.views._expire_checkout`.
2. In the storefront's `create_booking`, when a PayMongo checkout session was created but a later step failed (for
   example, saving its ID), expire that session as well as releasing the hold.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Review constraints:
  - "No external HTTP call inside a DB transaction."
  - "PayMongo metadata `booking_id` only; no personal data in logs or error messages."
  - The Downstream rule: `PayMongoClient` is a context manager (`with get_client() as client:`) and is never used
    inside `atomic()`.
- `payments/confirm.py:202-209`:
  ```python
  def _expire_session(checkout_session_id: str) -> None:
      """Best effort: a session left open could still take a payment, which would then need a
      refund. A failure is logged; the booking is released either way."""
      try:
          with get_client() as client:
              client.expire_checkout_session(checkout_session_id)
      except Exception as error:
          log_error("payment.expire_failed", error, session=checkout_session_id)
  ```
  Its one caller is `release_checkout` (:231, `transaction.on_commit(partial(_expire_session, …))`). Rename it to
  `expire_session`, and generalise the docstring: best effort, call it outside any transaction (directly, or through
  `on_commit`), never raises, and logs the session ID only.
- `dashboard/views.py:177-185` `_expire_checkout` is the same function. Delete it. In `cancel_view` (~:204) use
  `transaction.on_commit(partial(expire_session, booking.checkout_session_id))`, imported from `payments.confirm`.
  Remove the now-unused imports (`get_client`, and `log_error` if nothing else uses it). The module docstring's last
  sentence stays true.
- `dashboard/tests/test_schedule.py:137-140` `mock_client` patches `views.get_client`, which no longer exists. Repoint
  it to `payments.confirm.get_client` (`from payments import confirm`; `monkeypatch.setattr(confirm, "get_client",
  factory)`) and fix its docstring. The tests at ~:570-625 (session expired on commit, failure logged, not expired
  for a confirmed booking) must pass unchanged otherwise.
- `storefront/views.py:288-309` (`create_booking`, after `create_hold` committed; there's no `ATOMIC_REQUESTS`, so this
  runs outside any transaction):
  ```python
  try:
      with get_client() as client:
          session = client.create_checkout_session(...)
      booking.checkout_session_id = session.id
      booking.save(update_fields=["checkout_session_id", "updated_at"])
  except (PayMongoError, PaymentsConfigError) as error:
      log_error("booking.checkout_failed", error, ref=booking.reference)
      _release_failed_hold(booking)
      return json_response({"error": "payments_unavailable"}, status=503)
  except Exception as error:
      log_error("booking.checkout_failed", error, ref=booking.reference)
      _release_failed_hold(booking)
      raise
  ```
  Set `session = None` before the `try`. In **both** `except` branches, after `_release_failed_hold(booking)`, call
  `expire_session(session.id)` if `session is not None`. A direct call is right here: no transaction is open. Add a
  short comment: "created, but its ID wasn't saved: nobody can reach it, and it could still take a payment."
- Tests in `storefront/tests/test_bookings_api.py` (copy `FakePayMongo` :33-69, `use_fake_paymongo`, `post`,
  `booking_body`):
  - Give `FakePayMongo` an `expire_checkout_session(self, session_id)` that records into `self.expired: list[str]`
    and returns None.
  - New test: wrap the original `Booking.save` with `monkeypatch`. The wrapper raises `django.db.DatabaseError` only
    when `"checkout_session_id" in (update_fields or ())`, and otherwise delegates to the original:
    `create_hold`'s `objects.create` and `holds.release` also call `save`, and must keep working. Patch
    `payments.confirm.get_client` to the same fake. `post(...)` raises
    `DatabaseError` (the test client re-raises; use `pytest.raises`). The booking ends `expired` (slots freed, no
    `SlotLock` rows) and `fake.expired == [SESSION_ID]`.
  - New test: `create_checkout_session` raising `PayMongoError` (existing `use_fake_paymongo(monkeypatch, error=…)`)
    → 503 and `fake.expired == []`.
  - Show the first new test fails on the old code.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Call PayMongo inside `transaction.atomic()` or before the hold commits.
- Log anything but the session ID and reference.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
! grep -rnw --include='*.py' -e '_expire_checkout' -e '_expire_session' apps/backend
! grep -n 'get_client' apps/backend/dashboard/views.py
```
- `uv run pytest storefront/tests/test_bookings_api.py dashboard/tests/test_schedule.py payments -q` passes.
