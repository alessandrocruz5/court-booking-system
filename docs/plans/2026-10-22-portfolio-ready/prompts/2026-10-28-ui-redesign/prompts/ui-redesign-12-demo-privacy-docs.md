---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 12
unit: CBS-20
status: todo
model: opus
effort: medium
depends_on: [11]
parallel_group: D
files:
  create: []
  modify:
    - apps/backend/bookings/demo.py
    - apps/backend/bookings/tests/test_demo.py
    - apps/web/app/privacy/page.tsx
    - docs/runbook.md
  delete: []
---
# 12 · Demo check-ins, privacy notice, runbook

## Task
1. `seed_demo` marks today's in-progress demo bookings as checked in, so the desk and grid have realistic states.
2. `/privacy` mentions the check-in time.
3. The runbook gets the migration and rollout steps.

## Context
- `bookings/demo.py` is **high-stakes**.
  - After seeding, set `checked_in_at` (start + 0–10 min, deterministic from the reference) and `checked_in_by=None` on demo bookings that are confirmed, today, and started.
  - Use `checkin`'s rules: don't bypass them for future ones.
  - Keep the demo markers (`is_demo`, `@example.com`, `+63900000xxxx`).
- `/privacy` must match what's stored. Add the time staff checked you in, kept with the booking. No change to retention: anonymization doesn't touch `checked_in_at`, which isn't personal data on its own.
- `docs/runbook.md`:
  - a "Check-in migration (0003)" step: apply with `MIGRATE_DATABASE_URL` from a laptop **before** merging the Release that ships CBS-18/19
  - verify with `manage.py showmigrations bookings`
  - rollback: the columns are nullable and unused by the old code, so no contract step is needed

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && pnpm build
grep -n '0003' docs/runbook.md
```
