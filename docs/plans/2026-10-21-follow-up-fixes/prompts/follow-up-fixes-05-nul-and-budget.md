---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 05
unit: CBS-14
status: done
model: sonnet
effort: medium
depends_on: [04]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/dashboard/schedule.py
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/forms.py
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/tests/test_schedule.py
    - apps/backend/dashboard/tests/test_bookings.py
  delete: []
---
# 05 · NUL-byte 404s; viewer budget after validation

## Task
1. A NUL byte in a dashboard booking reference URL or in the add form's `?court=` gives a 404 instead of a 500.
2. The demo viewer's write budget (`_viewer_write_allowed`) is charged only by a create whose form is valid.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Postgres refuses NUL in text, and psycopg raises `ValueError` before the query runs, so these crash with a 500:
  - `dashboard/urls.py` `<str:reference>` paths → `dashboard/schedule.py:228-230` `get_booking(reference)` (used by
    `booking_panel`, `cancel_view`) and `dashboard/queries.py:614-616` `get_booking(*, role, reference, now=None)`
    (used by `booking_detail_view`), both `.filter(reference=reference)`.
  - `dashboard/forms.py` `StaffBookingForm.for_cell` (`Court.objects.filter(code=court_code, …)`) from
    `views._new_panel`'s `request.GET.get("court")`.
  Pattern to copy, `queries.py:419-420`: "Postgres refuses a NUL in a string, so it is dropped rather than left to
  raise." Here, return None for a value containing `"\x00"` (before querying) in those three functions, so the
  existing `None → Http404` paths answer. Keep the URL patterns. Form fields are already covered: Django's
  `CharField` rejects NUL, and `ModelChoiceField` turns lookup errors into validation errors.
- `dashboard/views.py` `_create` (~:247) today:
  ```python
  role = request.staff_role
  if not _viewer_write_allowed(request):
      return _panel_message(request, DEMO_LIMIT, 429)
  now = timezone.now()
  if role == Role.VIEWER and schedule.viewer_live_bookings(request.user, now) >= DEMO_LIVE_CAP:
      return _panel_message(request, DEMO_FULL, 429)
  form = StaffBookingForm(request.POST, demo_until=_demo_until(role, now))
  if not form.is_valid():
      return _form_response(request, form)
  ```
  Reorder so validation is first: build the form and return `_form_response` if it's invalid, then the budget, then
  the `DEMO_LIVE_CAP` check, then `create_staff_booking`. This matches the storefront rule "Invalid requests don't
  count against the rate limits" (CBS-6). `cancel_view` already checks `can_cancel` before the budget; leave it.
- Tests (copy the fixtures and helpers already in each file: `owner`, `viewer`, `HX`, `NEW`, `form_data`,
  `booking_url`, `cancel_url`, `WRITE_LIMIT` from `views`):
  - `test_schedule.py`: `GET /dashboard/schedule/booking/KC-%00AAAA/` (owner, `HX`) → 404; `POST …/KC-%00AAAA/cancel/`
    → 404; `GET NEW?court=%00&space=F&hour=10&date=<TODAY>` → 404.
  - `test_schedule.py`: the viewer posts an invalid form (for example a block with no note) `WRITE_LIMIT + 1` times,
    each getting the form error; then one valid create succeeds ("Booking added."). Reuse the pinned-clock fixture
    the existing budget test uses (~:860-920).
  - `test_bookings.py`: `GET /dashboard/bookings/KC-%00AAAA/` (owner) → 404.
  - Show the NUL tests fail on the old code (the test client re-raises the database adapter's exception, a 500), and
    the budget test too.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change URL patterns, the budget numbers or the cap.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
```
- `uv run pytest dashboard -q` passes, including the four NUL cases and the budget case.
