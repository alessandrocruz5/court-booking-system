---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 10
unit: CBS-20
status: todo
model: sonnet
effort: medium
depends_on: [09]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/dashboard/templates/dashboard/bookings.html
    - apps/backend/dashboard/templates/dashboard/booking_detail.html
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/dashboard/tests/test_bookings.py
  delete: []
---
# 10 · Bookings list and detail restyle

## Task
Restyle `bookings.html` (toolbar, table, pills) and `booking_detail.html` to the spec.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Staff.dc.html` (startTab=bookings).
- Same GET params, htmx `#results` partial, pagination and sort as today (`queries.parse_list_params`).
- The status segmented control is a set of radio-styled links or labels over the existing `status` param, including the derived `checked_in` and `completed` from 06. Plain `confirmed` still means every confirmed booking (the derived filters are additive).
- Each row is a link to `booking_detail` with `back_query`. Columns as in the spec. The sport tag comes from `tag-{sport}`.
- Footer: "Showing {n} of {total} bookings" from the page object.
- Detail page: the key/value card. When `detail.can_check_in` (06 added it to `queries.BookingDetail`), add Check in as a plain POST form to `dashboard:check_in` with `return=detail` (09 added that branch). Cancel stays.
- Tests: update the markup assertions you change and list them. Add one: the `status=checked_in` filter lists only checked-in bookings.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
cd apps/backend && uv run pytest dashboard -q
```
