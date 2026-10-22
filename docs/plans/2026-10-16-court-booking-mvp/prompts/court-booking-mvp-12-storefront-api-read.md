---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 12
unit: CBS-6
status: done
model: opus
effort: high
depends_on: [11]
parallel_group: L
files:
  create:
    - apps/backend/storefront/__init__.py
    - apps/backend/storefront/apps.py
    - apps/backend/storefront/auth.py
    - apps/backend/storefront/payloads.py
    - apps/backend/storefront/views.py
    - apps/backend/storefront/urls.py
    - apps/backend/storefront/tests/__init__.py
    - apps/backend/storefront/tests/test_auth.py
    - apps/backend/storefront/tests/test_catalog_availability.py
    - apps/backend/storefront/tests/test_contract.py
    - docs/api/README.md
    - docs/api/fixtures/catalog.json
    - docs/api/fixtures/availability.json
    - docs/api/fixtures/error.json
  modify:
    - apps/backend/config/settings.py
    - apps/backend/config/urls.py
    - apps/backend/.env.example
    - turbo.json
  delete: []
---
# 12 · Storefront API: auth, catalog and availability

## Task
Create the `storefront` Django app: the JSON API that only the Next.js server calls. Add the service-token guard and
the two read endpoints, `GET /api/v1/catalog` and `GET /api/v1/availability`. Pin the contract in
`docs/api/fixtures/*.json` with a shape-checking test that the web app's tests will also read.

## Context
- Repo root: `/Users/alessandrocruz/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`; `config.settings_test` sets `INTERNAL_API_TOKEN = "t" * 40`).
  `settings.INTERNAL_API_TOKEN` is read from env, and gunicorn refuses to start without it (32+ characters).
- Already there, read these:
  - `bookings/rules.py`: `OPEN_HOUR`, `CLOSE_HOUR`, `WINDOW_DAYS`, `MAX_HOURS`, `HOLD_MINUTES`, `SPORTS`, `COURT_COUNTS`, `Sport`,
    `Coverage`, `BookingRuleError(.code)`, `bookable_dates(now)`.
  - `bookings/pricing.py`: `rate_table()`, `PEAK_FROM_HOUR`, `is_peak`.
  - `bookings/availability.py`: `availability(*, day, sport, coverage, hours, now=None) -> list[CourtAvailability(code,
    name, starts: list[StartOption(hour, price_centavos, peak)])]`.
  - `bookings/models.py`: `Court`.
- **`storefront/auth.py`**: `def require_service_token(view)`, a decorator that also applies `csrf_exempt`. It reads
  `Authorization: Bearer <token>`.
  - If `settings.INTERNAL_API_TOKEN` is shorter than 32 characters → 503 `{"error":"unavailable"}` (fail closed).
  - A missing or wrong token → 401 `{"error":"unauthorized"}`, compared with `hmac.compare_digest` on bytes.
  - Log `api.unauthorized` with no header value.
  - Every response from a decorated view, including errors, gets `Cache-Control: no-store`.
- **`storefront/payloads.py`**: pure builders that return dicts.
  - `catalog_payload() -> dict`. It's **deterministic** (it doesn't depend on `now`):
    ```json
    {"venue": {"name": "Kalaro Courts", "time_zone": "Asia/Manila"},
     "hours": {"open": 7, "close": 23}, "window_days": 7, "max_hours": 3, "hold_minutes": 20,
     "peak": {"weekdays_from_hour": 17, "weekends_all_day": true},
     "sports": [{"id": "basketball", "label": "Basketball", "court_kind": "basketball", "court_count": 2,
                 "coverages": ["full", "half"],
                 "rates": {"full": {"off_peak": 120000, "peak": 160000}, "half": {"off_peak": 70000, "peak": 90000}}},
                …volleyball (coverages ["full"]), tennis, badminton, pickleball…]}
    ```
    `court_count` comes from `bookings.rules.COURT_COUNTS[court_kind]`, so the catalog **never queries the DB**:
    every landing-page visit calls it, and a query would wake Neon. Use the order basketball, volleyball, tennis, badminton,
    pickleball. The labels are title case.
  - `availability_payload(day, sport, coverage, hours, courts) -> dict`:
    `{"date": "YYYY-MM-DD", "sport", "coverage", "hours", "courts": [{"code", "name", "starts": [{"hour", "price_centavos", "peak"}]}]}`.
- **`storefront/views.py`** (GET only, `@require_service_token`):
  - `catalog` → 200 `catalog_payload()`.
  - `availability_view`: query parameters `date` (ISO), `sport`, `coverage` (default `full`) and `hours` (default 1).
    - A bad or missing field → 400 `{"error": "invalid_request", "fields": [<names>]}`. Never echo values.
    - A `BookingRuleError` → 400 `{"error": <code>}`, e.g. `outside_window`.
    - Otherwise 200 with the payload.
  - Every JSON response goes through one helper, `json_response(data, status)`, that sets `no-store`.
- **`storefront/urls.py`** under `/api/v1/`: `catalog` and `availability`. In `config/urls.py`, add
  `path("api/v1/", include("storefront.urls"))`. Add `"storefront"` to `INSTALLED_APPS`.
- **`.env.example`** (backend): expand the `INTERNAL_API_TOKEN` comment. It's shared with `apps/web`, generated with
  `python3 -c "import secrets; print(secrets.token_urlsafe(40))"`, and server only.
- **Contract** (`docs/api/`):
  - `README.md` documents each endpoint, the auth header, every status code and error code, and the rule that **every
    contract change updates the fixtures, both test suites, and `apps/web/src/lib/api/schemas.ts`** (once that file
    exists).
  - `fixtures/catalog.json` is the **exact** output of `catalog_payload()` with the 18 seeded courts.
  - `fixtures/availability.json` is a realistic example: basketball, half, 2 hours, both courts, a few starts.
  - `fixtures/error.json` is `{"error": "invalid_request", "fields": ["date"]}`.
  - Format the JSON with 2-space indentation and a final newline, so Prettier's `format:check` passes. Run
    `pnpm format` if needed.
- **`turbo.json`**: the fixtures live outside both packages, so Turbo's default inputs miss them, and a fixture edit
  would replay a cached green test. Give the `test` task
  `"inputs": ["$TURBO_DEFAULT$", "$TURBO_ROOT$/docs/api/fixtures/**"]`, keeping `dependsOn` and `outputs`. Check that
  `pnpm turbo run test --dry=json` lists the fixture files among `@cb/backend#test`'s inputs.
- **Tests**:
  - `test_auth.py`:
    - No header → 401. Wrong token → 401. A token differing in the last character → 401.
    - Right token → 200.
    - With `settings.INTERNAL_API_TOKEN = ""` → 503.
    - Every response has `no-store`, and POST to `catalog` → 405.
  - `test_catalog_availability.py`:
    - Volleyball only offers `full`.
    - `court_count` is 2/2/4/12/12, and `GET /api/v1/catalog` runs zero queries (`django_assert_num_queries(0)`).
    - Availability with hours=3 never offers a start after 20.
    - A booked hour disappears. Create it with `bookings.holds.create_staff_booking`.
    - The date today + 7 → 400 `outside_window`.
    - `sport=curling` → 400 `invalid_request` with `fields == ["sport"]`.
  - `test_contract.py`:
    - `catalog` equals `fixtures/catalog.json` **exactly**.
    - A helper, `assert_same_shape(actual, fixture)`, checks recursively that the keys and JSON types match (lists are
      compared element-wise against the fixture's first element).
    - The availability response and the error response have the same shape as their fixtures.
    - Find the fixtures by path: `Path(settings.BASE_DIR).parent.parent / "docs/api/fixtures"`.
- Review constraints: **internal API** (constant-time token, fail closed); **no caching** (`no-store`); **personal
  data** (no customer data on these endpoints).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add DRF or any serializer library.
- Add CORS headers. Browsers never call this API.
- Add the booking, checkout or lookup endpoints. That's prompt 13.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm format:check
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest storefront -q
```
