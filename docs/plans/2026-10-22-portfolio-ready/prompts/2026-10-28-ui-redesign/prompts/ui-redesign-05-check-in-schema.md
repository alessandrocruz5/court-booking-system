---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 05
unit: CBS-18
status: todo
model: opus
effort: high
depends_on: []
parallel_group: B
files:
  create:
    - apps/backend/bookings/migrations/0003_booking_check_in.py
    - apps/backend/bookings/checkin.py
    - apps/backend/bookings/tests/test_checkin.py
  modify:
    - apps/backend/bookings/models.py
  delete: []
---
# 05 · Booking check-in: columns, migration and service

## Task
Add `Booking.checked_in_at` and `Booking.checked_in_by` (expand-only), plus `bookings.checkin.check_in()`.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv). Postgres runs at `localhost:54329`.
- `bookings/models.py` and `*/migrations/**` are **high-stakes**.
  - Expand/contract only.
  - The migration is applied by the owner from a laptop with `MIGRATE_DATABASE_URL` **before** the backend that reads it deploys (see the plan's Rollout).
- The fields:
  - `checked_in_at = models.DateTimeField(null=True, blank=True)`
  - `checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")`
  - A `CheckConstraint` named `booking_check_in_needs_confirmed`: `Q(checked_in_at__isnull=True) | Q(status=Status.CONFIRMED)`. A booking cancelled after check-in would violate it, so `cancel_booking` must clear it. **Check `bookings/holds.py` `cancel_booking` first.** If it can cancel a confirmed booking, drop the constraint and say so in the report. Don't edit `holds.py` here.
  - No new index.
- Grants: the new columns are on an existing table, so `cb_app` DML already covers them.
- `bookings/checkin.py`: `check_in(booking, *, by, now) -> bool`.
  - Inside `transaction.atomic()`, re-read the row with `select_for_update()`.
  - It succeeds only when `status == CONFIRMED`, `source != BLOCK`, `checked_in_at is None`, `local_today(now) == starts_at` local date, and `ends_at > now`. It then sets both fields and `save(update_fields=[...])`.
  - Return True when it checked in, False when it was already checked in, and raise `CheckInError(code)` with codes `not_confirmed`, `is_block`, `not_today` or `ended`.
  - No HTTP and no logging of personal data.
- `test_checkin.py`:
  - one test per rule
  - idempotency (the second call returns False)
  - a concurrency-safe re-read: the row is changed to cancelled between load and call → `not_confirmed`
  - the migration applies on top of 0002

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.
- Edit `holds.py`, the storefront, or any applied migration.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
cd apps/backend && uv run python manage.py makemigrations --check --dry-run && uv run pytest bookings -q && cd ../..
pnpm --filter @cb/backend lint
```
