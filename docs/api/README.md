# Storefront API (`/api/v1/*`)

The JSON API the Django backend (`apps/backend/storefront`) serves to the Next.js storefront. **Only Next.js server
code calls it**: browsers never do, so there are no CORS headers and no CSRF tokens. The token never reaches a
client component.

## Contract rule

`fixtures/*.json` pin the contract, and both test suites read them: the backend's
`storefront/tests/test_contract.py`, and the web app's tests. **Every contract change updates, in the same PR:**

1. the fixtures in [`fixtures/`](fixtures/);
2. both test suites (backend and web);
3. `apps/web/src/lib/api/schemas.ts` (once that file exists);
4. this README.

`catalog.json` is the **exact** output of `GET /api/v1/catalog`. The other fixtures are realistic examples: the
backend checks that its responses have the same keys and JSON types (each list element against the fixture's first
element). The fixtures are inputs of every Turbo `test` task (`turbo.json`), so editing one never replays a cached
result.

## Authentication

Every request sends the shared service token:

```http
Authorization: Bearer <INTERNAL_API_TOKEN>
```

- The token is compared in constant time. It is the same value in both services, at least 32 characters, server
  only (never `NEXT_PUBLIC_`). Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(40))"`.
- A missing or wrong token answers `401 {"error": "unauthorized"}`. The backend logs `api.unauthorized`, never the
  header's value.
- If the backend's own `INTERNAL_API_TOKEN` is unset or shorter than 32 characters, every request answers
  `503 {"error": "unavailable"}` (fail closed).
- The token is checked before anything else, so an unauthenticated request learns nothing about the endpoint.

## Common behaviour

- Every response, errors included, sends `Cache-Control: no-store`.
- Bodies are JSON (`application/json`). Money is integer centavos (PHP). Hours are local hours (Asia/Manila), `7`
  to `22`; `23` is closing time.
- Error bodies never echo request values. No endpoint here returns personal data: a booking is described by
  `booking_summary` (below), which holds no name, email or mobile.
- `catalog` and `availability` allow only `GET`; the other endpoints allow only `POST`. Any other method answers
  `405` (an empty body).
- `POST` bodies are a JSON object of at most 4 KB. A larger body answers `413 {"error": "too_large"}`; a body that
  isn't a JSON object answers `400 {"error": "invalid_request", "fields": ["body"]}`.
- Timestamps are ISO-8601 in venue time, with the offset (`2026-10-30T14:20:00+08:00`). `date` and `start_hour` are
  local.
- A request never sets a price or a payment status: the server quotes the price, and payment status comes only
  from PayMongo, read on the server.

## Rate limits

Counted per client IP in Postgres, in fixed 10-minute windows, across all instances. The Next.js server sends the
visitor's IP as `client_ip`.

| Endpoint                       | Limit                | Over the limit                  |
| ------------------------------ | -------------------- | ------------------------------- |
| `POST /api/v1/bookings`        | 5 per IP per 10 min  | `429 {"error": "rate_limited"}` |
| `POST /api/v1/bookings/lookup` | 10 per IP per 10 min | `429 {"error": "rate_limited"}` |

On top of that, one email may hold at most 2 unpaid holds that haven't lapsed; a third create answers
`429 {"error": "too_many_holds"}`. Requests rejected as `invalid_request` are not counted.

## `GET /api/v1/catalog`

The venue, its rules and its rates. It never queries the database (every landing-page visit calls it), and it
doesn't depend on the current time.

| Status | Body                                             |
| ------ | ------------------------------------------------ |
| 200    | [`catalog.json`](fixtures/catalog.json), exactly |

Fields:

- `venue`: `name`, `time_zone` (IANA).
- `hours`: `open` and `close`, local hours. The last bookable hour starts at `close - 1`.
- `window_days`: bookable dates are today and the next `window_days - 1` days (local).
- `max_hours`: the longest booking, in hours. `hold_minutes`: how long an unpaid hold keeps its slot.
- `peak`: weekdays are peak from `weekdays_from_hour`; weekends are peak all day when `weekends_all_day`.
- `sports[]`, in display order (basketball, volleyball, tennis, badminton, pickleball): `id`, `label`,
  `court_kind` (`basketball`, `tennis` or `multi`; sports sharing a kind share its courts), `court_count`,
  `coverages` (`full`, plus `half` for basketball), and `rates[coverage]` with `off_peak` and `peak` centavos per
  hour.

## `GET /api/v1/availability`

Free start hours per court for one search. It is advisory: the slot is only claimed when a hold is created.

Query parameters:

| Name       | Required | Format                                         | Default |
| ---------- | -------- | ---------------------------------------------- | ------- |
| `date`     | yes      | `YYYY-MM-DD`, a local date                     |         |
| `sport`    | yes      | a catalog sport `id`                           |         |
| `coverage` | no       | `full` or `half`                               | `full`  |
| `hours`    | no       | an integer; the rules allow `1` to `max_hours` | `1`     |

Response `200` ([`availability.json`](fixtures/availability.json)): `date`, `sport`, `coverage`, `hours`, and
`courts[]` (the sport's active courts in display order) with `code`, `name` and `starts[]`. Each start has `hour`
(the first hour), `price_centavos` (the total for all `hours`) and `peak` (whether the first hour is peak). A start
is listed when the whole span is free and ends by closing time, and, for today, when its hour hasn't begun. For
`half`, a start is listed when either half of the court is free. A court with no free start has `starts: []`.

| Status | Body                                                | When                                                                   |
| ------ | --------------------------------------------------- | ---------------------------------------------------------------------- |
| 200    | the availability payload                            | The search is valid.                                                   |
| 400    | `{"error": "invalid_request", "fields": [<names>]}` | A parameter is missing or malformed, or `sport`/`coverage` is unknown. |
| 400    | `{"error": "outside_window"}`                       | `date` is before today or past the booking window.                     |
| 400    | `{"error": "coverage_not_allowed"}`                 | The sport doesn't offer that coverage (e.g. `half` volleyball).        |
| 400    | `{"error": "invalid_hours"}`                        | `hours` is outside `1`…`max_hours`.                                    |
| 401    | `{"error": "unauthorized"}`                         | See [Authentication](#authentication).                                 |
| 405    | empty                                               | Not `GET`.                                                             |
| 503    | `{"error": "unavailable"}`                          | The backend's token isn't configured.                                  |

`fields` lists the failing parameter names in the order `date`, `sport`, `coverage`, `hours`
([`error.json`](fixtures/error.json)).

## `booking_summary`

The booking object in the checkout-status and lookup responses
([`checkout-status.json`](fixtures/checkout-status.json), [`booking-lookup.json`](fixtures/booking-lookup.json)):

| Field             | Type           | Notes                                                                             |
| ----------------- | -------------- | --------------------------------------------------------------------------------- |
| `reference`       | string         | `KC-` plus 6 characters.                                                          |
| `status`          | string         | `pending`, `confirmed`, `expired`, `cancelled` or `needs_refund`.                 |
| `court`           | object         | `code` and `name`.                                                                |
| `sport`           | string         | A catalog sport `id`.                                                             |
| `coverage`        | string         | `full` or `half`.                                                                 |
| `half`            | string or null | `A` or `B` for `half`; null for `full`.                                           |
| `date`            | string         | `YYYY-MM-DD`, local.                                                              |
| `start_hour`      | number         | The first local hour.                                                             |
| `hours`           | number         | The duration.                                                                     |
| `price_centavos`  | number         | The price quoted and snapshotted when the hold was created.                       |
| `hold_expires_at` | string or null | When an unpaid hold lapses; null once paid.                                       |
| `paid_at`         | string or null | Null until paid.                                                                  |
| `payment_method`  | string or null | PayMongo's source type (`card`, `gcash`, `paymaya`, `grab_pay`); null until paid. |

## `POST /api/v1/bookings`

Create a 20-minute hold on a slot, then a PayMongo test checkout session for it.

```json
{
  "court": "tn-2",
  "sport": "tennis",
  "coverage": "full",
  "date": "2026-10-31",
  "start_hour": 18,
  "hours": 2,
  "customer": { "name": "Ana Reyes", "email": "ana@example.com", "mobile": "09171234567" },
  "consent": true,
  "client_ip": "203.0.113.10"
}
```

Validation (failures are listed in `fields`, in this order, by name only):

| Field             | Rule                                                       |
| ----------------- | ---------------------------------------------------------- |
| `court`           | An active court `code`.                                    |
| `sport`           | A catalog sport `id`.                                      |
| `coverage`        | `full` or `half`.                                          |
| `date`            | `YYYY-MM-DD`.                                              |
| `start_hour`      | An integer.                                                |
| `hours`           | An integer.                                                |
| `customer.name`   | 2 to 80 characters after trimming.                         |
| `customer.email`  | A valid email, at most 254 characters. Stored lowercased.  |
| `customer.mobile` | `^(\+63\|0)9\d{9}$`, no spaces. Stored as `+639XXXXXXXXX`. |
| `consent`         | Literally `true`. Its time is stored with the booking.     |
| `client_ip`       | An IPv4 or IPv6 address.                                   |

Then the rate limits, then the booking rules (window, hours, coverage, court kind). The price is quoted on the
server; a `price` or `status` in the body is ignored. Once the hold has committed, the backend creates the checkout
session. PayMongo receives the booking ID as metadata, a line item such as
`Tennis Court 2 · Tennis · Sat 31 Oct, 6–8 PM`, and `Kalaro Courts booking KC-… (test mode)`: no customer data. If
PayMongo fails, the hold is released at once and the slot is free again.

| Status | Body                                                    | When                                                        |
| ------ | ------------------------------------------------------- | ----------------------------------------------------------- |
| 201    | [`booking-created.json`](fixtures/booking-created.json) | The hold and the checkout session exist.                    |
| 400    | `{"error": "invalid_request", "fields": [<names>]}`     | See the validation table.                                   |
| 400    | `{"error": <rule code>}`                                | A booking rule failed (see [Error codes](#error-codes)).    |
| 409    | `{"error": "slot_taken"}`                               | Another booking holds the slot.                             |
| 413    | `{"error": "too_large"}`                                | The body is over 4 KB.                                      |
| 429    | `{"error": "rate_limited"}`                             | 5 creates from this IP in the window.                       |
| 429    | `{"error": "too_many_holds"}`                           | This email already has 2 unexpired unpaid holds.            |
| 503    | `{"error": "payments_unavailable"}`                     | PayMongo failed or isn't configured; the hold was released. |

`201` fields: `reference`, `checkout_url` (on `checkout.paymongo.com`; redirect the visitor there),
`checkout_session_id` (keep it server-side, in the `cb_checkout` cookie), `hold_expires_at` and `price_centavos`.

## `POST /api/v1/checkout/confirm`

The success page's check. Body: `{"checkout_session_id": "cs_…"}`. The backend reads the session from PayMongo (only
when the booking isn't already paid) and records a paid payment through `confirm_payment()`. Nothing in the
success page's URL is trusted.

| Status | Body                                                              | When                                                                                      |
| ------ | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 200    | `{"status": <status>, "booking": booking_summary \| null}`        | Always, once the body is valid ([`checkout-status.json`](fixtures/checkout-status.json)). |
| 400    | `{"error": "invalid_request", "fields": ["checkout_session_id"]}` | The ID is missing or not a string.                                                        |

`status`:

| Value          | `booking` | Meaning                                                                                               |
| -------------- | --------- | ----------------------------------------------------------------------------------------------------- |
| `confirmed`    | yes       | Paid and confirmed.                                                                                   |
| `pending`      | yes       | The hold is live and no payment has arrived yet.                                                      |
| `expired`      | yes       | The hold lapsed with no payment. A payment that still arrives later re-claims the slot if it is free. |
| `cancelled`    | yes       | The hold was released from the cancel page, with no payment.                                          |
| `needs_refund` | yes       | Paid after the hold lapsed and the slot was taken; staff refund it.                                   |
| `not_found`    | null      | No booking has this session (or the session isn't ours).                                              |
| `unavailable`  | null      | PayMongo or the database couldn't be reached; try again.                                              |

## `POST /api/v1/checkout/release`

The cancel page. Body: `{"checkout_session_id": "cs_…"}`. Releases a pending hold's slots, then expires its PayMongo
session after the release commits (a lapsed hold's session is expired too).

| Status | Body                                                              | When                                                                                |
| ------ | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 200    | `{"status": "released" \| "already_paid" \| "not_found"}`         | Once the body is valid ([`checkout-release.json`](fixtures/checkout-release.json)). |
| 400    | `{"error": "invalid_request", "fields": ["checkout_session_id"]}` | The ID is missing or not a string.                                                  |

`already_paid`: the booking is confirmed (or awaiting a refund) and is never cancelled here.

## `POST /api/v1/bookings/lookup`

Find a booking by reference and email. Body: `{"reference": "KC-7Q4M2X", "email": "ana@example.com", "client_ip":
"203.0.113.10"}`. The reference is trimmed and uppercased, the email trimmed and lowercased. Anonymized bookings
are never found.

| Status | Body                                                | When                                                                         |
| ------ | --------------------------------------------------- | ---------------------------------------------------------------------------- |
| 200    | `{"booking": booking_summary}`                      | Found ([`booking-lookup.json`](fixtures/booking-lookup.json)).               |
| 400    | `{"error": "invalid_request", "fields": [<names>]}` | `reference` or `email` is empty, or `client_ip` isn't an IP (in that order). |
| 404    | `{"error": "not_found"}`                            | No match. Identical whether the reference or the email was wrong.            |
| 429    | `{"error": "rate_limited"}`                         | 10 lookups from this IP in the window.                                       |

## Error codes

| Code                    | Status | Meaning                                                          |
| ----------------------- | ------ | ---------------------------------------------------------------- |
| `invalid_request`       | 400    | Malformed or missing parameters, named in `fields`.              |
| `outside_window`        | 400    | The date is outside the bookable window.                         |
| `coverage_not_allowed`  | 400    | The sport doesn't offer that coverage.                           |
| `invalid_hours`         | 400    | The duration is outside `1`…`max_hours`.                         |
| `outside_hours`         | 400    | The span starts before opening or ends after closing.            |
| `in_the_past`           | 400    | The start hour has already begun.                                |
| `wrong_court_for_sport` | 400    | The court isn't of the sport's kind.                             |
| `unknown_sport`         | 400    | Not a catalog sport (normally caught as `invalid_request`).      |
| `court_inactive`        | 400    | The court is closed (normally caught as `invalid_request`).      |
| `unauthorized`          | 401    | Missing or wrong bearer token.                                   |
| `not_found`             | 404    | Lookup: no booking matches the reference and email.              |
| `slot_taken`            | 409    | Another booking holds the slot.                                  |
| `too_large`             | 413    | The body is over 4 KB.                                           |
| `rate_limited`          | 429    | Too many requests from this IP; see [Rate limits](#rate-limits). |
| `too_many_holds`        | 429    | The email already has 2 unexpired unpaid holds.                  |
| `payments_unavailable`  | 503    | PayMongo failed or isn't configured; the hold was released.      |
| `unavailable`           | 503    | The backend isn't configured to serve the API.                   |
