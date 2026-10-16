---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 21
unit: CBS-9
status: todo
model: sonnet
effort: high
depends_on: [20]
parallel_group: U
files:
  create:
    - apps/backend/dashboard/__init__.py
    - apps/backend/dashboard/apps.py
    - apps/backend/dashboard/urls.py
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/templates/dashboard/base.html
    - apps/backend/dashboard/templates/dashboard/overview.html
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/dashboard/static/dashboard/htmx.min.js
    - apps/backend/dashboard/tests/__init__.py
    - apps/backend/dashboard/tests/test_overview.py
  modify:
    - apps/backend/config/settings.py
    - apps/backend/config/urls.py
  delete: []
---
# 21 · Dashboard shell and overview

## Task
Create the `dashboard` app: the HTMX staff dashboard's shell (header with venue, role and sign-out; nav; vendored
htmx) and the **Overview** page an owner would want each morning:
- today's bookings, utilization and revenue
- 7- and 30-day revenue (gross, fees, net) and revenue by sport
- a utilization heatmap by weekday × hour
- the next three hours' bookings
- alerts for `needs_refund` and active holds

All data comes from `dashboard/queries.py`, which applies the viewer's masking.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`; `TIME_ZONE = "Asia/Manila"`).
- Already there:
  - `templates/base.html`, with blocks `title`, `styles`, `header`, `content` and `scripts`. It holds the test-mode
    banner and links `core/static/core/base.css`, which defines the tokens `--ink/--paper/--court/--clay/--line/--error`
    and buttons.
  - `accounts.decorators.staff_required`, which sets `request.staff_role` and adds `no-store`.
  - `accounts.roles`: `Role`, `can_see_personal_data(role)`. `/dashboard/login/`, `/dashboard/demo/` and
    `/dashboard/logout/` (POST) exist via `accounts.urls`, which is included at `dashboard/` in `config/urls.py`.
  - Models in `bookings.models`: `Court(code, name, kind, sort_order)`, and `Booking` with `status`
    (pending/confirmed/expired/cancelled/needs_refund), `source` (online/walk_in/block), `sport`, `coverage`, `half`,
    `starts_at`, `ends_at`, `hours`, `price_centavos`, `fee_centavos`, `net_centavos`, `payment_method`, `paid_at`,
    `customer_name/email/mobile`, `hold_expires_at` and `is_demo`. Also `SlotLock`.
  - `bookings.rules`: `OPEN_HOUR=7`, `CLOSE_HOUR=23`, `SPACES`, `TIME_ZONE`.
- Django 6 template partials (`{% partialdef name %}…{% endpartialdef %}`, rendered as `"template.html#name"`) are
  built in. **Check the installed Django's docs and source for the exact syntax.** HTMX is detected with
  `request.headers.get("HX-Request") == "true"`. Don't add django-htmx.
- **Vendor htmx 2.0.11**: run `npm pack htmx.org@2.0.11`, which gives an npm-registry tarball with an integrity check.
  Copy `package/dist/htmx.min.js` to `dashboard/static/dashboard/htmx.min.js` unmodified, then delete the tarball. No CDN.
- **`dashboard/base.html`** (extends `base.html`):
  - `<meta name="htmx-config" content='{"includeIndicatorStyles":false,"allowEval":false,"allowScriptTags":false,"historyCacheSize":0}'>`.
    This keeps htmx CSP-safe (no eval) and keeps masked pages out of the history cache.
  - `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`, done via the `header` block or a wrapping element.
  - `<script src="{% static 'dashboard/htmx.min.js' %}" defer></script>` and a link to `dashboard/dashboard.css`.
  - A header with "Kalaro Courts · Staff", the user's role as an uppercase badge (OWNER/VIEWER), the sign-out form
    (POST, CSRF), and a nav with just **Overview** for now. Prompts 22 and 23 add Schedule and Bookings.
  - For the viewer, a note: "You're exploring the demo: customers' contact details are masked."
  - **No inline scripts. No `hx-on` attributes** (they need eval).
- **`dashboard/queries.py`** (the only place views get data from):
  - Masking helpers, applied **here**, never in templates:
    - `mask_email("juan.cruz@example.com")` → `"j•••@example.com"`
    - `mask_mobile("+639171234567")` → `"•••67"`
    - `mask_name("Juan Dela Cruz")` → `"Juan D."`
    - For `Role.VIEWER`, every row's personal fields go through these. The owner sees them raw.
  - `def overview(*, role, now=None) -> Overview` (frozen dataclasses):
    - `today`: the count of confirmed bookings (not blocks) starting today, gross revenue today, and utilization %.
      Utilization is booked space-hours (confirmed online and walk-in) ÷ (20 spaces × 16 hours − blocked space-hours).
      Basketball has spaces A and B, everything else F, for 2×2 + 4 + 12 = 20 spaces.
    - `revenue_7d` and `revenue_30d`: gross, fees and net. Online confirmed bookings use `price` / `fee` / `net`;
      walk-ins are cash with fee 0. Use `starts_at` in the window, ending now.
    - `by_sport_30d`: per sport, the count and gross.
    - `heatmap`: for each weekday (Mon–Sun) and hour (7–22), utilization % over the last 28 full days, as integers
      0–100.
    - `upcoming`: confirmed bookings starting within the next 3 hours, ordered by start, with the court name, sport,
      half, time range, source and a masked or raw name.
    - `alerts`: the count of `needs_refund` bookings and the count of active `pending` holds.
  - Use aggregate queries (`Sum`, `Count`, `values(...).annotate(...)`), not per-row Python loops over the 30 days.
    The heatmap may group in Python over one query of SlotLocks.
- **`dashboard/views.py`**: `overview_view` with `@staff_required`, GET only, rendering `dashboard/overview.html` with
  the `Overview`. Format money as `₱1,234` with a small template filter in `views.py`, or pre-format in the dataclass.
- **`overview.html`**:
  - A KPI card row. A red alert (`role="status"`) when `needs_refund > 0`: "N paid bookings need a refund (payment
    arrived after the hold expired)."
  - Revenue by sport as horizontal bars. Widths come from CSS classes `w-0`…`w-100` in steps of 5, generated in
    `dashboard.css`; or use inline `style` widths, which CSP allows (`style-src 'unsafe-inline'`). Prefer classes.
  - The heatmap as a `<table>` with `heat-0`…`heat-5` cell classes, a caption, and `<th scope>` headers.
  - The upcoming list. Make it readable at 375 px: the tables scroll inside a wrapper, never the page.
- **`dashboard/urls.py`**: `""` → overview, name `dashboard:overview`. In `config/urls.py`, add
  `path("dashboard/", include("dashboard.urls"))` **after** the accounts include, plus `path("", RedirectView(url="/dashboard/"))`.
  Add `"dashboard"` to `INSTALLED_APPS`.
- **Tests** (`test_overview.py`). Build data with `bookings.holds.create_staff_booking` and `create_hold`, then mark
  some online bookings confirmed with payment fields directly.
  - Anonymous → 302 to login.
  - Viewer and owner → 200, with the banner and the role badge.
  - Revenue sums are correct (walk-in fee 0).
  - Utilization for a day with a full basketball booking for 1 h = 2 / 320 space-hours.
  - A block reduces the denominator.
  - The viewer's upcoming names are masked (`"Juan D."`), and the raw email is never in the HTML for the viewer.
    The owner sees the full name.
  - The `needs_refund` alert shows only when there are any.
  - The page has no `<script>` without `src`, and no `hx-on`.
  - Unit-test the mask helpers.
- Review constraints:
  - **Staff access**: `@staff_required`, masking in `queries.py`.
  - **Personal data**: the viewer never receives raw contact details.
  - **CSP**: no inline scripts, no eval.
  - **Test-mode banner.**

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add schedule or bookings pages, or write actions. Those are prompts 22–23.
- Load anything from a CDN or add JS beyond the vendored htmx.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest dashboard accounts -q
DJANGO_SETTINGS_MODULE=config.settings env -i PATH="$PATH" HOME="$HOME" uv run python manage.py collectstatic --noinput --dry-run
```
- Run it locally: migrate, `seed_staff`, then `ALLOW_DEMO_SEED=1 … seed_demo`. Open `http://localhost:8000/` →
  login → **Explore the owner demo**. The overview shows non-zero KPIs and the heatmap, the badge says VIEWER, and
  there are no CSP violations in the browser console.
