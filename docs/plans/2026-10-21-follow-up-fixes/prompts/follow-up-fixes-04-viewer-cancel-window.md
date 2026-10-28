---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 04
unit: CBS-14
status: done
model: opus
effort: high
depends_on: [03]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/accounts/roles.py
    - apps/backend/accounts/tests/test_access.py
    - apps/backend/dashboard/schedule.py
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/tests/test_schedule.py
  delete: []
---
# 04 · Viewer cancels only bookings that haven't ended

## Task
The public demo viewer can cancel a demo booking, walk-in or block **only while it hasn't ended**
(`booking.ends_at > now`). The owner is unchanged. `accounts.roles.can_cancel` gets a required keyword `now`, and
every caller passes the request's clock.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Locked decision (MVP plan), narrowed here by the user on 2026-10-21: "The viewer can operate the demo … cancel demo
  or staff-made bookings … Only the owner can cancel a real visitor's online booking." Today the viewer can also cancel
  yesterday's real walk-ins, which rewrites revenue history.
- Review constraint: "permissions are checked on the server"; dashboard views use `accounts.roles` on the server and
  the templates only reflect it.
- `accounts/roles.py:44-53`:
  ```python
  def can_cancel(role: Role | None, booking) -> bool:
      """Whether `role` may cancel `booking`. Only a pending or confirmed booking can be cancelled;
      the viewer only when it's demo data or not an online booking."""
      if booking.status not in _CANCELLABLE:
          return False
      if role == Role.OWNER:
          return True
      if role == Role.VIEWER:
          return booking.is_demo or booking.source != Source.ONLINE
      return False
  ```
  Change it to `can_cancel(role, booking, *, now: datetime) -> bool`. The viewer branch adds
  `and booking.ends_at > now`. Update the docstring.
- **Clock:** the dashboard tests pin `NOW = datetime(2026, 11, 2, 12, tzinfo=rules.TIME_ZONE)` by patching
  `dashboard.views.timezone` (`test_schedule.py:162-164`, `test_bookings.py:111-113`), and `NOW` is in the future.
  So `roles` must never read the clock itself, and the views must take `now` from `timezone.now()` **in
  `dashboard/views.py`**. Callers to update:
  - `dashboard/schedule.py:171` (`_booking_cell`, already has `now`): pass `now=now`.
  - `dashboard/schedule.py:245` `booking_detail(booking, *, role)`: add `now: datetime | None = None`, default
    `now = now or timezone.now()` (the pattern of `build_grid` :204-206), and pass it at :252.
  - `dashboard/queries.py:614` `get_booking(*, role, reference)`: add `now: datetime | None = None` with the same
    default, and pass it at :623.
  - `dashboard/views.py`:
    - `booking_panel`: `schedule.booking_detail(booking, role=…, now=timezone.now())`.
    - `booking_detail_view`: `queries.get_booking(…, now=timezone.now())`.
    - `cancel_view`: compute `now = timezone.now()` **before** `can_cancel(role, booking, now=now)` and reuse it for
      `holds.cancel_booking`.
- Tests:
  - `accounts/tests/test_access.py:140-157`: pass a fixed `now` and give `_booking()` an `ends_at` (read the helper
    first). Keep every existing row, and add: viewer + ended walk-in → False; viewer + ended demo → False; viewer +
    walk-in ending in one minute → True; owner + ended confirmed → True.
  - `dashboard/tests/test_schedule.py`, with the existing fixtures (`viewer`, `owner`, `HX`, `cancel_url`,
    `booking_url`, the booking factories):
    - The viewer's `POST` cancel of a walk-in that ended before `NOW` → 403 with `CANT_CANCEL`, and the booking stays
      confirmed.
    - Its panel (`GET booking_url`) has no "Cancel booking" button.
    - The owner can still cancel it.
- `grep -rn 'can_cancel(' apps/backend --include='*.py'` must show `now=` at every call.
- The autouse `pinned_clock` patches only `dashboard.views.timezone`. So any new **direct** call to
  `queries.get_booking` or `schedule.booking_detail` in a test that asserts `can_cancel` must pass `now=NOW`.
  Otherwise it reads the real clock, and the test starts failing after 2026-11-02.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change the owner's rule, the `_CANCELLABLE` statuses, or `bookings.holds`.
- Read the clock inside `accounts/roles.py`.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
grep -rn --include='*.py' 'can_cancel(' apps/backend | grep -v 'def can_cancel' | grep -v 'now='   # prints nothing
```
- The new viewer-ended-walk-in test fails on the old code.
