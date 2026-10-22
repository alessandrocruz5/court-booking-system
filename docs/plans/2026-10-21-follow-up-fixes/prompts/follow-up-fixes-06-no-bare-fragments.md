---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 06
unit: CBS-14
status: done
model: sonnet
effort: high
depends_on: [05]
parallel_group: C
files:
  create:
    - apps/backend/dashboard/templates/dashboard/fragment_page.html
  modify:
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/tests/test_schedule.py
  delete: []
---
# 06 · Full pages, never bare fragments, without htmx

## Task
A request without `HX-Request: true` to a schedule fragment endpoint gets a full page (the dashboard shell and the
"Fictional venue · Test mode, no real payments" banner) or a redirect to one, never a bare partial. htmx responses
stay exactly as they are.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Review constraint: "Every page of both apps shows 'Fictional venue · Test mode, no real payments'." The banner comes
  from `templates/base.html`, which `dashboard/base.html` extends. A bare partial has no banner.
- `dashboard/views.py` (read it whole): `_is_htmx(request)`. The fragment responses:
  - `booking_panel` (GET) → `schedule.html#panel`.
  - `new_view` GET → `_new_panel` → `schedule.html#form`; `new_view` POST → `_create`.
  - `cancel_view` (POST) → `_grid_response` → `schedule.html#grid`. Its `return=detail` branch already handles
    non-htmx via `_to_detail` (303); keep it.
  - `_panel_message(request, message, status)` (403/429 refusals) and `_form_response(request, form)` (form errors)
    render partials with `HX-Retarget`/`HX-Reswap`.
  - `schedule_view` and `bookings_view` already return full pages without htmx; leave them.
- New behaviour **only when `not _is_htmx(request)`**:
  - `booking_panel`: after the existing 404 check, `HttpResponseRedirect(reverse("dashboard:booking_detail",
    args=[reference]))`.
  - `new_view` GET (`_new_panel`): redirect to `reverse("dashboard:schedule") + "?date=YYYY-MM-DD"` for
    `_requested_day(request.GET.get("date"), now)`. Do this after the permission check in `new_view`, so a 403 still
    renders.
  - Successful POSTs (`_create`, `cancel_view` without `return=detail`): `HttpResponseRedirect(<schedule>?date=<day>,
    status=303)`. Put this in `_grid_response`, which already has `day`.
  - `_panel_message` and `_form_response`: render `dashboard/fragment_page.html` with the same context, the same
    status, and `fragment` set to `"dashboard/schedule.html#panel"` or `"dashboard/schedule.html#form"`.
- `fragment_page.html`: `{% extends "dashboard/base.html" %}`, `dashboard_title` "Schedule", and in
  `dashboard_content`: `<div hx-disable>{% include fragment %}</div>` followed by a link back to the schedule (`{% url
  'dashboard:schedule' %}`). `hx-disable` is needed because `dashboard/base.html` loads htmx, and the `#form`
  partial's `hx-post` / `hx-target="#grid"` would otherwise go to a `#grid` this page doesn't have. With it, the form
  posts as a plain HTML form. Add a comment saying so. Django 6's built-in template partials accept `"template.html#partial"` in `include` and
  `get_template`; prove it with a test. The `#form` partial already has `{% csrf_token %}`. Follow the template
  conventions in `dashboard/base.html`'s comment: no inline scripts or styles, no `hx-on`.
- Tests in `test_schedule.py` (fixtures `owner`, `viewer`, `HX`, `NEW`, `form_data`, `booking_url`, `cancel_url`; the
  pinned clock), all **without** `headers=HX`:
  - `GET booking_url(ref)` → 302 to `/dashboard/bookings/<ref>/`; an unknown reference is still 404.
  - `GET NEW?court=…&hour=…&date=…` → 302 to `/dashboard/schedule/?date=…`.
  - `POST NEW` valid → 303 to the schedule for that date, and the booking exists.
  - `POST NEW` invalid → 200 full page containing the banner text, `<html`, `hx-disable` and the form error.
  - The viewer's `POST cancel_url` of a real online booking → 403 full page with the banner and `CANT_CANCEL`.
  - The owner's `POST cancel_url` → 303 to the schedule for the booking's day.
  - One htmx test of each endpoint (existing ones are fine) still gets the partial, with no `<html`.
  Run the whole dashboard suite: update only tests that assumed a bare fragment without `HX`.

## Do not
- Touch files outside the `files` list (`schedule.html` included). If you must, stop and report why.
- Change any htmx response, status code or header.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
```
- `uv run pytest dashboard -q` passes, and every non-htmx case above has a test.
