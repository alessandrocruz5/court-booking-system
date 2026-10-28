---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 12
unit: CBS-21
status: done
model: sonnet
effort: medium
depends_on: [11]
parallel_group: D
files:
  create: []
  modify:
    - apps/web/app/privacy/page.tsx
    - docs/runbook.md
  delete: []
---
# 12 · Privacy notice and runbook

## Task
1. `/privacy` mentions the check-in time.
2. The runbook gets the migration and rollout steps.

Demo check-in seeding was dropped in the audit: `cb-nightly` reseeds at 03:00 Manila, before any booking that day has started. **Don't edit `bookings/demo.py`.**

## Context
- `/privacy` must match what's stored. Add the time staff checked you in, kept with the booking. No change to retention: anonymization doesn't touch `checked_in_at`, which isn't personal data on its own.
- `docs/runbook.md`:
  - in "Demo data and nightly job", one line: demo bookings are never pre-checked-in; the viewer can check in today's demo bookings from the Front desk
  - a "Check-in migration (0003)" step: apply with `MIGRATE_DATABASE_URL` from a laptop **before** merging the Release that ships CBS-19/CBS-20
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
