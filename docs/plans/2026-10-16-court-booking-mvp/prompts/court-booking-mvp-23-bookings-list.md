---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 23
unit: CBS-10
status: todo
model: sonnet
effort: high
depends_on: [22]
parallel_group: W
files:
  create:
    - apps/backend/dashboard/templates/dashboard/bookings.html
    - apps/backend/dashboard/templates/dashboard/booking_detail.html
    - apps/backend/dashboard/tests/test_bookings.py
  modify:
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/urls.py
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/templates/dashboard/base.html
  delete: []
---
# 23 · Bookings list and detail

## Task
Add `/dashboard/bookings/`, a searchable, filterable, paginated list of every booking whose state lives in the URL and
updates through HTMX swaps. Add `/dashboard/bookings/<reference>/` for the full detail. The owner sees personal data;
the viewer sees it masked **in the query layer**, and the viewer's search can't be used to confirm a customer's email
or mobile.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`).
- Already there (read them):
  - `dashboard/queries.py` (the masking helpers `mask_name`, `mask_email` and `mask_mobile`; `overview()`),
    `dashboard/views.py`, `dashboard/urls.py`, `dashboard/schedule.py`, and the templates `dashboard/base.html`
    (nav: Overview, Schedule), `overview.html` and `schedule.html` (with partials). Django 6 template partials are
    built in.
  - `accounts.decorators.staff_required`, and `accounts.roles` (`Role`, `can_see_personal_data`, `can_cancel`). The
    schedule's booking panel and cancel endpoint exist at `/dashboard/schedule/booking/<reference>/` and `…/cancel/`.
  - `Booking` fields: reference, court, sport, coverage, half, starts_at, ends_at, hours, source, status,
    price_centavos, fee/net, payment_method, payment_id, paid_at, customer_name/email/mobile, consent_at, note,
    is_demo, created_by, created_at, cancelled_at, anonymized_at.
- Pattern reference, read only: `/Users/alessandrocruz/Code/fun-run-website/packages/db/src/admin/queries.ts` (masking
  in the query layer; the viewer's search matches name and reference only) and
  `/Users/alessandrocruz/Code/fun-run-website/apps/admin/src/lib/search-params.ts` (the list state lives in the URL
  and is parsed defensively).
- **`queries.py`**: add the following.
  - `@dataclass(frozen=True) ListParams(q: str, status: str | None, sport: str | None, source: str | None,
    date_from: date | None, date_to: date | None, sort: str, page: int)`.
  - `def parse_list_params(querydict) -> ListParams`. Anything invalid falls back to its default. `q` is capped at
    60 characters. `sort` is one of `-starts_at` (default), `starts_at`, `-created_at` or `-price_centavos`. `page` is ≥ 1.
  - `def list_bookings(*, role, params) -> Page` with 25 per page and `select_related("court")`.
    - Search: the owner matches reference, name, email and mobile (`icontains`). **The viewer matches reference and
      name only.**
    - Rows are frozen dataclasses with masked values for the viewer, including `mask_name`.
  - `def get_booking(*, role, reference) -> BookingDetail | None`. It's masked the same way, includes the payment
    fields (method, fee, net, paid_at) and `consent_at`, and has `can_cancel`.
- **Views** (`@staff_required`, GET):
  - `bookings_view` renders the full page. With `HX-Request`, render only the `results` partial.
  - The filter form uses `hx-get` with `hx-trigger="change, keyup changed delay:300ms from:#q"`,
    `hx-target="#results"` and `hx-push-url="true"`, and is a normal GET form without JS.
  - Pagination links are real `href`s plus `hx-get`.
  - `booking_detail_view` → 404 for an unknown reference. It shows everything for the role, a Cancel button (posting
    to the existing schedule cancel endpoint) only when `can_cancel`, a "needs refund" callout for `needs_refund`,
    and an "anonymized" note when `anonymized_at` is set.
  - The detail page's Cancel form posts `return=detail` to that endpoint. In `views.py`, `cancel_view` then answers
    with `HX-Redirect: /dashboard/bookings/<reference>/` (a 303 to the same URL without htmx) instead of the schedule
    grid partial. Without `return=detail` it behaves as before, and prompt 22's viewer limits still apply.
- **Templates**:
  - `bookings.html`: the filter bar (search, status, sport, source, from/to dates, sort), a count summary, and
    `{% partialdef results %}` with a table on desktop and cards at 375 px. Add status badges and source tags, plus a
    demo tag when `is_demo`.
  - `booking_detail.html`: a back link that preserves the list's query string. The list builds detail links with the
    current params, the same pattern as fun-run's `detailHref`.
- **`base.html`**: add a **Bookings** nav item after Schedule.
- **`urls.py`**: `bookings/` and `bookings/<str:reference>/`.
- **Tests** (`test_bookings.py`):
  - Anonymous → 302.
  - The owner searching by email finds the booking. **The viewer searching by the same email finds nothing.** The
    viewer searching by name or reference finds it.
  - The viewer's list and detail HTML never contain the raw email or mobile, and names show as `"Juan D."`. The owner
    sees them raw.
  - The status, sport and source filters, the date range and the sorts work. Page 2 works, and a bad page → page 1.
  - An HTMX request returns only the results partial.
  - Detail → 404 for an unknown reference.
  - The cancel button is absent for the viewer on a real online booking and present on a demo one.
  - An anonymized booking shows the note and no contact details.
  - Cancelling from the detail page (`return=detail`) redirects back to the detail page, not to a grid partial.
- Review constraints:
  - **Staff access** and **masking in the query layer**.
  - **Personal data**: the viewer's search can't confirm contact details.
  - **CSP**: no inline JS.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add CSV export or any write actions beyond linking to the existing cancel endpoint.
- Mask only in templates.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest dashboard -q
```
