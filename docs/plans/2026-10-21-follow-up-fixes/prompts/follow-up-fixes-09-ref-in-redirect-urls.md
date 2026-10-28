---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 09
unit: CBS-16
status: done
model: opus
effort: medium
depends_on: [03]
parallel_group: E
files:
  create: []
  modify:
    - apps/backend/storefront/views.py
    - apps/backend/storefront/tests/test_bookings_api.py
  delete: []
---
# 09 · Success and cancel URLs name the booking

## Task
The PayMongo checkout session's `success_url` and `cancel_url` carry the booking's reference as `?ref=<reference>`,
so the web's result pages can tell which of a browser's checkouts PayMongo is returning from.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Why: the web keeps one `cb_checkout` cookie per browser. With two tabs checking out, the second overwrites the
  first, so tab A's success page checks B's session, and A's cancel releases B's hold. Prompts 10–11 make the cookie
  hold several `reference → session` entries; the `ref` here picks one.
- Review constraint: "Payment status comes only from the server … URL parameters are never trusted." This stays true:
  `ref` only selects which of the visitor's own cookie entries the web asks the backend about. Never put anything else
  in these URLs: no session ID, no status, no personal data. "PayMongo metadata: `booking_id` only" is unaffected.
- `storefront/views.py` `create_booking` (~:290-299):
  ```python
  success_url=f"{settings.SITE_URL}/book/success",
  cancel_url=f"{settings.SITE_URL}/book/cancelled",
  ```
  Change both to append `?ref={booking.reference}`. A reference is `KC-` plus 6 Crockford base32 characters
  (`bookings/references.py`), so it's URL-safe as it is. Add a one-line comment that `ref` only picks the visitor's
  own cookie entry on the web and is never trusted for status.
- `storefront/tests/test_bookings_api.py:164-165` asserts the old URLs. Change them to
  `f"http://localhost:3000/book/success?ref={booking.reference}"` and the cancelled equivalent. The PII loop below
  them must still pass (a reference isn't personal data).
- No API response, fixture or `schemas.ts` change: the contract (`docs/api/fixtures`) is untouched.
- Deploy independence: the current web pages ignore `searchParams`, so this is safe with the old web. With the new
  web, Deploy rolls out `cb-backend` before `cb-web`. A checkout started in between has a `?ref=` URL and a legacy
  cookie, and prompt 10's `pickCheckout` handles that with a legacy-entry fallback.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change the API response body, the metadata, or anything else in `create_checkout_session`'s call.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
```
- `uv run pytest storefront -q` passes, with the new URL asserts.
