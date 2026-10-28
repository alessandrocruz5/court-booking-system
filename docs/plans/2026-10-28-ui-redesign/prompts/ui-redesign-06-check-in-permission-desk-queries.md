---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 06
unit: CBS-19
status: done
model: opus
effort: high
depends_on: [05]
parallel_group: B
files:
  create:
    - apps/backend/dashboard/desk.py
    - apps/backend/dashboard/tests/test_desk_queries.py
  modify:
    - apps/backend/accounts/roles.py
    - apps/backend/accounts/tests/test_access.py
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/views.py
  delete: []
---
# 06 · can_check_in, desk queries, derived statuses

## Task
1. Add `roles.can_check_in(role, booking, *, now)`.
2. Add `dashboard/desk.py` with the Front desk's read models.
3. Make `queries.py` aware of "Checked in" and "Completed".

## Context
- `accounts/**` is **high-stakes**. Permissions are checked on the server; templates only reflect them.
- `can_check_in` mirrors `can_cancel`:
  - The owner: whenever `checkin.check_in` would succeed.
  - The viewer: only when `booking.is_demo or booking.source != Source.ONLINE`, and never a real visitor's online booking.
  - `now` is required.
- `desk.py` (all masking goes through the existing `queries.name_for`, `mask_email` and `mask_mobile`):
  - `normalise_query(text) -> str`: trim and uppercase. Add `KC-` when there's no `-` and the text looks like 6 Crockford characters. Reject `\x00` (return "").
  - `lookup(role, text, now) -> DeskResult | None`: an exact reference match.
    - `DeskResult` carries: reference, status_label, pill class, masked name and contact, amount, court label, sport label, time label, `warning: str | None`, `can_check_in`, `checked_in_clock`, schedule day.
    - The warning copy and precedence follow the spec's Front desk section.
  - `suggest(role, text, now, limit=5)`: filter with the existing `queries._search(role, text)` (`dashboard/queries.py:569`), excluding blocks. Don't write a new search: `_search` already limits the viewer to demo bookings' names, so the viewer can never confirm a real customer's name.
  - `arriving(role, now, within_hours=queries.UPCOMING_HOURS)`, `on_court(role, now)`, `stats(now)`.
    - **Reuse the overview's aggregates; don't re-derive them.** Import from `queries`: `_today(now)` (bookings and revenue today), `_alerts(now).active_holds`, `_lock_counts`, `SPACE_COUNT` and `_clock`. New SQL only for walk-ins today and the arriving and on-court rows (which need the reference, `status_key` and `can_check_in`).
    - Stats: bookings today, walk-ins today, revenue today, spaces in use now out of `SPACE_COUNT`, and active holds.
- `queries.py`:
  - Add `status_key(booking, now) -> str`, the **only** place the derived status is decided (09's schedule imports it):
    - a block → `block`
    - confirmed and `ends_at <= now` → `completed`
    - confirmed and `checked_in_at` set → `checked_in`
    - otherwise `booking.status` (`confirmed | pending | cancelled | needs_refund | expired`)
  - Add `checked_in` ("Checked in") and `completed` ("Completed") to `STATUS_CHOICES` as **additive** filters:
    - `status=checked_in` = confirmed, `checked_in_at` set, `ends_at > now`
    - `status=completed` = confirmed, `ends_at <= now`
    - plain `status=confirmed` is **unchanged** (`status=confirmed`). The pagination tests in `test_bookings.py:434-471` list 30 past confirmed bookings under it and must stay green untouched.
  - `parse_list_params` checks `status` against `Status.values` today (`queries.py:420`): check it against the `STATUS_CHOICES` keys instead.
  - `list_bookings(*, role, params, now: datetime | None = None)`: `now = now or timezone.now()`. In `views.bookings_view`, pass `now=timezone.now()` (the tests pin the clock through `views.timezone`). That one line is the only `views.py` change.
  - `_row` and `get_booking` take `now` and expose `status_key` and `checked_in_clock`. `BookingDetail` also gets `can_check_in` (from `roles.can_check_in`), next to `can_cancel`; 10's detail page needs it.
  - Keep the masking where it is. Thread `now` the way 2026-10-21 prompt 04 did.
- Tests:
  - `test_access.py`: the `can_check_in` matrix.
  - `test_desk_queries.py`: normalising, viewer masking, viewer name search matching demo bookings only (never a real one), each warning, the arriving window and its LATE/NEXT tags, `status_key` precedence (a checked-in booking that has ended is `completed`), the `checked_in` and `completed` filters, and plain `confirmed` still listing ended bookings.
  - Pin `now` like the existing `pinned_clock`.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
cd apps/backend && uv run pytest accounts dashboard -q
```
