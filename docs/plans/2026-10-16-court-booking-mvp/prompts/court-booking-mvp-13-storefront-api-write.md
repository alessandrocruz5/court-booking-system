---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 13
unit: CBS-6
status: todo
model: opus
effort: xhigh
depends_on: [12]
parallel_group: M
files:
  create:
    - apps/backend/storefront/tests/test_bookings_api.py
    - apps/backend/storefront/tests/test_checkout_api.py
    - docs/api/fixtures/booking-created.json
    - docs/api/fixtures/checkout-status.json
    - docs/api/fixtures/checkout-release.json
    - docs/api/fixtures/booking-lookup.json
  modify:
    - apps/backend/storefront/views.py
    - apps/backend/storefront/payloads.py
    - apps/backend/storefront/urls.py
    - apps/backend/storefront/tests/test_contract.py
    - docs/api/README.md
  delete: []
---
# 13 · Storefront API: bookings, checkout and lookup

## Task
Add the write side of the storefront API:
- **create a booking**: a 20-minute hold, then a PayMongo checkout session.
- **confirm a checkout**: the success page.
- **release a checkout**: the cancel page.
- **look up a booking** by reference and email.

Add rate limits, and extend the contract fixtures and tests.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`). Read `storefront/{auth,payloads,views,urls}.py`. They have
  `require_service_token` (constant-time bearer token, `csrf_exempt`, `no-store`), `json_response(data, status)`,
  `invalid_request` with a `fields` list, and the contract helper `assert_same_shape` in `tests/test_contract.py`.
- The services you call (read their signatures):
  - `bookings.holds`: `Customer(name, email, mobile)`, `create_hold(*, court, sport, coverage, day, start_hour, hours,
    customer, now=None) -> Booking`, `release(booking, *, status, now=None) -> bool`, `SlotTaken`.
  - `bookings.rules`: `BookingRuleError(.code)`, `Status`, `Sport`.
  - `core.ratelimit.hit(scope, ident, *, limit, window_seconds) -> bool`.
  - `payments.paymongo`: `get_client()`, `PayMongoError`. `payments.env.PaymentsConfigError`.
  - `payments.confirm`: `check_checkout(id) -> CheckResult(status, booking)` (confirmed, pending, needs_refund,
    not_found or unavailable) and `release_checkout(id) -> "released" | "already_paid" | "not_found"`.
    As built in CBS-5: `check_checkout` raises `RuntimeError` inside `atomic()` (it calls PayMongo), so the view must
    not wrap it in a transaction, and tests that reach it unmocked need
    `django_db(transaction=True, serialized_rollback=True)`. It returns `pending` for an `expired` or `cancelled`
    booking with no paid payment; decide what the confirm endpoint answers for that. `release_checkout` also expires
    the PayMongo session of an `expired` hold (after commit). `PayMongoClient` is a context manager:
    `with get_client() as client:`. `create_checkout_session`'s `line_item_name`/`description` go to PayMongo
    verbatim: no personal data in them. `PAYMONGO_WEBHOOK_SECRET` must be 24+ characters.
  - `settings.SITE_URL`: the web origin, no trailing slash.
- **Endpoints**: all `POST`, JSON body ≤ 4 KB (larger → 413 `{"error":"too_large"}`), `@require_service_token`, `no-store`.
  - **`POST /api/v1/bookings`**. Body: `{court, sport, coverage, date, start_hour, hours, customer: {name, email,
    mobile}, consent, client_ip}`.
    1. Validate. `court` is an active court code. `name` is 2–80 characters after trimming. `email` passes Django's
       `EmailValidator`, is ≤ 254 characters, and is stored lowercased. `mobile` matches `^(\+63|0)9\d{9}$` and is
       stored normalized to `+639XXXXXXXXX`. `consent` must be literally `true`. `client_ip` must parse with
       `ipaddress.ip_address`. Errors → 400 `{"error":"invalid_request","fields":[…]}` with names only, never values.
    2. `hit("booking_create", client_ip, limit=5, window_seconds=600)`. If refused → 429 `{"error":"rate_limited"}`.
    3. If 2 or more `pending` bookings with `hold_expires_at > now` share this email → 429 `{"error":"too_many_holds"}`.
    4. `create_hold(...)`. `SlotTaken` → 409 `{"error":"slot_taken"}`. A `BookingRuleError` → 400 `{"error": code}`.
    5. **After the hold has committed**, call `get_client().create_checkout_session(...)` with:
       - `booking_id=str(booking.id)`
       - `line_item_name`, e.g. `"Tennis Court 2 · Tennis · Sat 18 Oct, 6–8 PM"`, built from the court, the sport label
         and the local time. **No customer data.**
       - `amount_centavos=booking.price_centavos`
       - `description=f"Kalaro Courts booking {booking.reference} (test mode)"`
       - `success_url=f"{SITE_URL}/book/success"` and `cancel_url=f"{SITE_URL}/book/cancelled"`

       Save `checkout_session_id` on the booking. On `PayMongoError` or `PaymentsConfigError`, `release(booking,
       status="expired")`, then 503 `{"error":"payments_unavailable"}`, and log `booking.checkout_failed` with the
       reference plus the status and codes.
    6. 201 `{"reference", "checkout_url", "checkout_session_id", "hold_expires_at": ISO-8601, "price_centavos"}`.
  - **`POST /api/v1/checkout/confirm`**. Body: `{checkout_session_id}` → `check_checkout()` →
    200 `{"status": …, "booking": booking_summary | null}`.
  - **`POST /api/v1/checkout/release`**. Body: `{checkout_session_id}` → 200 `{"status": release_checkout(...)}`.
  - **`POST /api/v1/bookings/lookup`**. Body: `{reference, email, client_ip}`.
    - `hit("booking_lookup", client_ip, limit=10, window_seconds=600)`. If refused → 429.
    - Match where `reference == upper(trimmed)`, the lowercased email is equal, and `anonymized_at` is null.
    - Found → 200 `{"booking": booking_summary}`. Not found → 404 `{"error":"not_found"}`. The not-found response is
      identical whether the reference or the email was wrong.
- **`payloads.booking_summary(booking) -> dict`**: `{"reference", "status", "court": {"code", "name"}, "sport",
  "coverage", "half", "date", "start_hour", "hours", "price_centavos", "hold_expires_at", "paid_at",
  "payment_method"}`. Use local date and hour, ISO strings, and null when absent. **It holds no customer name, email
  or mobile.**
- **Fixtures**: `booking-created.json`, `checkout-status.json` (a confirmed example with a full `booking`),
  `checkout-release.json` and `booking-lookup.json`. Add them to `test_contract.py` with `assert_same_shape`. Update
  `docs/api/README.md` with each endpoint, its body, statuses and error codes, and the rate limits.
- **Tests**:
  - `test_bookings_api.py`. Mock `storefront.views.get_client` (or wherever you import it) with a fake whose
    `create_checkout_session` returns a `CheckoutSession` with ID `cs_test123` and URL
    `https://checkout.paymongo.com/cs_test123`.
    - Happy path → 201. The booking is pending with the session ID, the price matches `pricing.quote`, and
      `consent_at` is set.
    - Second booking for the same slot → 409.
    - 6th create from the same IP within 10 minutes → 429.
    - 3rd active hold for the same email → 429 `too_many_holds`.
    - `consent: false` → 400 with `fields` containing `consent`.
    - A bad mobile → 400, and the response body doesn't contain the submitted value.
    - Volleyball half → 400 `coverage_not_allowed`.
    - A PayMongo error → 503, and the slot is free again (a new booking succeeds).
    - The fake receives `booking_id` only and no customer data in any argument (assert the email isn't in any string
      argument).
  - `test_checkout_api.py`. Mock `check_checkout` and `release_checkout`, or exercise them through a fake client.
    - Confirm → payload shape. Release → `released`.
    - Lookup: right reference and email → 200; wrong email → 404; wrong reference → 404 with an identical body;
      lowercase reference works; an anonymized booking → 404; 11th lookup → 429.
    - Every endpoint without a token → 401.
  - Rate-limit tests pin the clock `core.ratelimit` reads (with `monkeypatch`), so a run can't straddle a window
    boundary.
- Review constraints:
  - **Payment status only from the server.**
  - **No external HTTP inside a DB transaction**: the checkout call happens after the hold commits.
  - **Slot integrity.**
  - **Personal data**: never in responses, logs or PayMongo metadata.
  - **Internal API**, and **no caching**.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Trust a `price` or `status` from the request body. Neither is accepted.
- Return customer fields from any endpoint.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm format:check
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest storefront payments bookings -q
```
