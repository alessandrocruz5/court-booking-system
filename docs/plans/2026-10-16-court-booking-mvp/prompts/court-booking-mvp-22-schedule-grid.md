---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 22
unit: CBS-10
status: done
model: opus
effort: high
depends_on: [21, 18]
parallel_group: V
files:
  create:
    - apps/backend/dashboard/schedule.py
    - apps/backend/dashboard/forms.py
    - apps/backend/dashboard/templates/dashboard/schedule.html
    - apps/backend/dashboard/tests/test_schedule.py
  modify:
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/urls.py
    - apps/backend/dashboard/templates/dashboard/base.html
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/bookings/holds.py
  delete: []
---
# 22 · Schedule grid: walk-ins, blocks and cancellations

## Task
Build `/dashboard/schedule/`, the screen a venue owner lives in. It's a day grid of every court (basketball split into
Half A and Half B) by hour, 07:00–23:00, colour-coded by booking type. Staff can click a booking to see details and
cancel it, or click a free cell to add a **walk-in** or a **block** (maintenance, events). Every action is an HTMX
partial swap, and every write goes through the slot engine with permissions checked on the server.

## Context
- Repo root: `/Users/alessandrocruz/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`).
- Already there (read them):
  - `dashboard/{views,urls,queries}.py` and `templates/dashboard/{base,overview}.html`. The base template sets the
    htmx config (no eval, no history cache), `hx-headers` with the CSRF token, the role badge, and a nav that only has
    Overview so far. `queries.py` holds the mask helpers `mask_name`, `mask_email` and `mask_mobile`.
  - `accounts.decorators.staff_required` (sets `request.staff_role`; for HTMX, an `HX-Redirect` to login).
  - `accounts.roles`: `Role`, `can_create_staff_booking`, `can_cancel(role, booking)` (the viewer can only cancel
    `is_demo` bookings or non-online sources), `can_see_personal_data`.
  - `bookings.availability.occupancy(day, *, now=None)`, which returns `{(court_id, space, hour): Booking}` for active locks.
  - `bookings.holds`: `create_staff_booking(*, source, court, sport, coverage, half, day, start_hour, hours,
    created_by, customer_name="", note="", is_demo=False, now=None) -> Booking`, `release(booking, *, status, now=None)
    -> bool`, `SlotTaken`.
  - `core.ratelimit.hit(scope, ident, *, limit, window_seconds) -> bool` (DB-backed, keyed on an HMAC) and
    `core.http.client_ip(request)`.
  - `bookings.rules`: `BookingRuleError(.code)`, `SPORTS`, `SPACES`, `OPEN_HOUR`, `CLOSE_HOUR`, `TIME_ZONE`,
    `validate_staff_request` (today to today + 30; must end after now).
  - Demo data from `seed_demo` fills the grid. `is_demo` rows are reseeded nightly.
- **`bookings/holds.py`**: add `def cancel_booking(booking: Booking, *, by_role: str, now=None) -> bool`. It's a thin
  wrapper that calls `release(booking, status="cancelled", now=now)` and logs `booking.cancelled` with the reference
  and role. It exists so the permission-checked call site is explicit. Don't change other functions.
- **`dashboard/schedule.py`**: `def build_grid(day, *, role, now=None) -> Grid`.
  - The rows: each court in `sort_order`. Basketball courts get two rows, "Court 1 · Half A" and "Court 1 · Half B".
    The columns are the hours 7–22.
  - Each cell is `free`, or a booking segment with its `source` (online/walk_in/block), `status` (confirmed/pending),
    `is_demo`, the reference, sport, the name masked for the viewer, `colspan` for consecutive hours of the same
    booking, and `can_cancel` (from `accounts.roles.can_cancel`).
  - A full-court basketball booking spans both half rows. Render it in both rows, each with its own segment.
  - Past hours on today are marked `past`, so no add action is offered.
- **`dashboard/forms.py`**: `StaffBookingForm` (Django Form) with `kind` (walk_in|block), `court` (code), `sport`
  (required for walk-in; must be valid for the court's kind), `coverage` and `half` (basketball only; volleyball is
  forced to full), `start_hour`, `hours` (1–3), `customer_name` (optional, ≤ 80) and `note` (required for a block, ≤ 120).
- **Views** (all `@staff_required`):
  - `schedule_view` (GET `?date=YYYY-MM-DD`, default today Manila). It renders the whole page: a date nav (‹ prev,
    today, next ›, a date input, limited to today − 30 … today + 30), a legend, and the grid. With `HX-Request`, render
    only the grid partial (`schedule.html#grid`). The date links use `hx-get` with `hx-target="#grid"`,
    `hx-push-url="true"`, and a real `href` fallback.
  - `booking_panel` (GET `/dashboard/schedule/booking/<reference>/`): a side-panel partial with the details (masked
    for the viewer), plus a Cancel button (`hx-post`, `hx-confirm`) **only if** `can_cancel`. For an online
    confirmed booking, the owner sees the note "Refund it in the PayMongo dashboard (test mode)."
  - `cancel_view` (POST): load the booking. If `not can_cancel(request.staff_role, booking)` → **403**, with a
    partial saying "You can't cancel this booking." Otherwise `cancel_booking(...)`, then return the refreshed grid
    partial plus an out-of-band toast: `<div id="toast" role="status" hx-swap-oob="true">Booking cancelled.</div>`.
    Don't use `HX-Trigger`: with no JS beyond htmx, nothing would listen for the event.
  - `new_panel` (GET `?court=&space=&hour=&date=`): a partial with the add form, prefilled. Only staff roles that pass
    `can_create_staff_booking` get it.
  - `create_view` (POST): validate the form. `create_staff_booking(..., created_by=request.user)`.
    - `SlotTaken` → re-render the form with "That time was just taken."
    - `BookingRuleError` → a fixed message per code.
    - Success → the refreshed grid partial.
    - Bookings the **viewer** creates get `is_demo=True`, so the nightly reseed cleans them up and other visitors see a
      tidy demo.
  - **Viewer write limits** (the demo account is public). Before `create_view` or `cancel_view` writes for the viewer,
    call `core.ratelimit.hit("staff_write", core.http.client_ip(request), limit=20, window_seconds=600)`. Refused →
    429 with a partial saying "Demo limit reached. Try again in a few minutes." The viewer can only create bookings
    from today to today + 6; a later date gets the form error "The demo takes bookings up to 6 days ahead." The owner
    has neither limit.
- **`schedule.html`**: the page, plus `{% partialdef grid %}`, `{% partialdef panel %}` and `{% partialdef form %}`.
  - The grid is a `<table>` in a horizontally scrolling wrapper, with sticky first-column court names.
  - The cells use classes `slot-online`, `slot-walkin`, `slot-block`, `slot-pending`, `slot-past` and `slot-free`.
    Append their rules, plus the sticky column, the panel and the toast, to `dashboard/static/dashboard/dashboard.css`.
    Use the tokens: court-green for online, ink for walk-in, a striped line colour for block, a dashed clay border for
    pending.
  - Every interactive cell is a `<button>` or `<a>` with an accessible label, e.g. "Tennis Court 2, 6 PM, free: add
    booking".
  - The side panel is `<aside id="panel" aria-live="polite">`.
- **`dashboard/base.html`**: add a **Schedule** nav item after Overview, and an empty
  `<div id="toast" role="status" aria-live="polite"></div>` for the out-of-band toasts.
- **`dashboard/urls.py`**: `schedule/`, `schedule/booking/<str:reference>/`, `schedule/booking/<str:reference>/cancel/`,
  `schedule/new/` (GET panel and POST create can share a view or be split).
- **Tests** (`test_schedule.py`):
  - Anonymous → 302, and HTMX anonymous → `HX-Redirect`.
  - The grid has 22 rows (18 courts + 2 extra half rows) × 16 hours.
  - A full basketball booking appears in both half rows.
  - HTMX GET returns only the grid partial (no `<html>`).
  - Walk-in create → confirmed, cash, priced by `pricing.quote`. A second walk-in on the same cell → "just taken".
  - A block requires a note, and a block on basketball fills both halves.
  - **Viewer cancelling a real online booking → 403, and the booking is unchanged.** Viewer cancelling a demo
    booking → cancelled. Owner cancelling an online booking → cancelled, with the locks gone.
  - Bookings created by the viewer have `is_demo=True`.
  - The viewer's panel HTML never contains the raw email or mobile.
  - POST without CSRF → 403. The test client enforces this with `enforce_csrf_checks=True`.
  - The viewer's 21st write within 10 minutes → 429 (pin the clock `core.ratelimit` reads); the owner isn't limited.
    A viewer walk-in for today + 7 → the form error. A cancel response carries the out-of-band `#toast` element.
- Review constraints:
  - **Staff access**: permissions are checked in the view, not only hidden in the template; `@staff_required` everywhere.
  - **Slot integrity**: writes go only through `bookings.holds`.
  - **Personal data**: masking in `queries.py`/`schedule.py`, never only in templates.
  - **CSP**: no inline JS, no `hx-on`.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Write `SlotLock` rows directly, or bypass `create_staff_booking` or `release`.
- Add drag-and-drop or any JS beyond htmx attributes.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest dashboard bookings accounts -q
```
- Run it locally with demo data, as the viewer. The schedule shows today full of bookings. Clicking a free cell → add
  a walk-in → the grid updates without a page reload. A real online booking (create one through the storefront API)
  shows no Cancel button for the viewer.
