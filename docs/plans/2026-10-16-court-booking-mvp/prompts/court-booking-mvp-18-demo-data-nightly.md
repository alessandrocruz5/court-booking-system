---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 18
unit: CBS-8
status: todo
model: opus
effort: high
depends_on: [17]
parallel_group: R
files:
  create:
    - apps/backend/bookings/demo.py
    - apps/backend/bookings/management/__init__.py
    - apps/backend/bookings/management/commands/__init__.py
    - apps/backend/bookings/management/commands/seed_demo.py
    - apps/backend/bookings/management/commands/nightly.py
    - apps/backend/bookings/tests/test_demo.py
    - apps/backend/bookings/tests/test_nightly.py
  modify:
    - docs/runbook.md
    - apps/backend/.env.example
  delete: []
---
# 18 · Demo data and nightly job

## Task
Make the demo look like a real, busy venue on any day someone opens it.
- **`manage.py seed_demo`** regenerates realistic, deterministic demo bookings from today − 30 to today + 6, and never
  touches real visitor bookings.
- **`manage.py nightly`** expires stale holds, anonymizes visitor personal data 7 days after a booking ends, prunes
  rate-limit rows and sessions, then reseeds. It runs as the Cloud Run Job `cb-nightly`, triggered by Cloud Scheduler.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`).
- Read these first:
  - `bookings/models.py` (`Court`, `Booking` with the `is_demo`, payment and customer fields, `SlotLock`).
  - `bookings/rules.py` (`TIME_ZONE`, `OPEN_HOUR`, `CLOSE_HOUR`, `SPORTS`, `Status`, `Source`, `slot_starts`, `spaces_for`).
  - `bookings/pricing.py` (`quote`, `is_peak`) and `bookings/references.py` (`new_reference`).
  - `bookings/holds.py`: `claim_slots(booking, spaces, starts, *, now)`, which must run inside `transaction.atomic()` and
    raises `SlotTaken`, plus `expire_stale_holds(*, now=None) -> int`.
  - `core/ratelimit.py`: `prune(*, older_than, now=None) -> int`.
- Pattern reference, read only: `/Users/alessandrocruz/Code/fun-run-website/packages/db/src/seed-registrations.ts`
  (fake people, `@example.com`, `+63900000xxxx`, an explicit guard) and the runbook's "Demo data" bullet
  (`/Users/alessandrocruz/Code/fun-run-website/docs/runbook.md`, around lines 375–390).
- **`bookings/demo.py`**: `def generate(*, today: date, now: datetime, rng: random.Random) -> int`.
  - Delete every `is_demo=True` booking first (their locks cascade).
  - For each day from today − 30 to today + 6, each court and each hour, decide occupancy with a simple model:
    - The base rate per hour band: 7–9 = 0.35, 9–16 = 0.2, 17–22 = 0.75. Weekends × 1.25, capped at 0.9.
    - Multi courts are the busiest; tennis peaks in mornings and evenings.
    - For basketball, about 30% of bookings are halves and 15% are volleyball (full).
    - Durations: 1 h 50%, 2 h 40%, 3 h 10%.
    - Sources: online 80% and walk-in 20%. Add one or two blocks a week, e.g. "Resurfacing" or "League night", on
      random courts.
  - Create each booking with `claim_slots` inside its own `atomic()`. **On `SlotTaken`, skip it**, so real visitor
    bookings always win.
  - Online demo bookings are `confirmed` with fake payments:
    - Method mix: gcash 55%, card 25%, paymaya 15%, grab_pay 5%.
    - Fees use **illustrative** rates in the constant `DEMO_FEE_RATES`: gcash 2.5%, paymaya 2%, grab_pay 2.2%, and
      card 3.5% + ₱15. Comment that these aren't PayMongo's actual pricing.
    - `net = price − fee`. `paid_at` falls between 1 and 72 hours before `starts_at`, and before `now`.
    - `payment_id = "pay_demo_<hex>"`.
  - People: a fixed list of about 60 common Filipino first and last names. Emails are `first.last.NN@example.com`;
    mobiles are `+63900000` plus 4 digits, the markers the dashboard and the anonymizer rely on.
    `consent_at = created_at`.
  - Return the count. Leave no `pending` demo holds.
- **`seed_demo` command**: refuse to run unless `os.environ.get("ALLOW_DEMO_SEED") == "1"` (exit code 2 with a clear
  message). Otherwise, `rng = random.Random(today.isoformat())`, which makes the same day give the same data. Mark
  it `# noqa: S311` (demo data, not security).
  Print the counts.
- **`nightly` command**: each step is logged with counts only, under logger `cb.nightly`. A failure in one step is
  logged by class name and doesn't stop the others; the exit code is 1 if any step failed.
  1. `expire_stale_holds()`.
  2. **Anonymize** non-demo bookings with `ends_at < now − 7 days` and `anonymized_at` null: set `customer_name=""`,
     `customer_email=None`, `customer_mobile=None` and `anonymized_at=now`. Keep the financial and slot data.
  3. `prune(older_than=timedelta(hours=1))` on the rate-limit table. Windows last at most 10 minutes, and `/privacy`
     promises deletion within a day.
  4. `call_command("clearsessions")`.
  5. If `ALLOW_DEMO_SEED == "1"`, call `demo.generate(...)` (same seeding as `seed_demo`).
- `apps/backend/.env.example`: add `ALLOW_DEMO_SEED=` with a comment: `1` lets `seed_demo` and `nightly` regenerate
  demo bookings; set it locally and on the `cb-nightly` job only.
- **`docs/runbook.md`**: append `## Demo data and nightly job`.
  - What it does and why (a live-looking demo, plus RA 10173 retention).
  - Running it locally: `ALLOW_DEMO_SEED=1 uv run --env-file .env python manage.py seed_demo`.
  - The Cloud Scheduler trigger, once, after this unit deploys: `gcloud scheduler jobs create http cb-nightly-trigger
    --location asia-southeast1 --schedule "0 3 * * *" --time-zone "Asia/Manila"` calling the Cloud Run Jobs `:run` API
    with an OAuth token for a service account that has `roles/run.invoker` on the job. Give the full command. This is
    free: 1 of the 3 free Scheduler jobs.
  - A manual run: `gcloud run jobs execute cb-nightly --region asia-southeast1`.
  - The nightly job is the only scheduled DB use (Neon CU-hours).
- **Tests**:
  - `test_demo.py`:
    - Generating twice with the same seed gives identical (court, starts_at, sport) sets.
    - Every demo row is `confirmed`, `is_demo`, `@example.com` and `+63900000…`.
    - Occupancy over the 37 days lands between 25% and 75% of court-hours.
    - A real (non-demo) confirmed booking keeps its slot and isn't deleted.
    - No demo booking is outside 07:00–23:00.
  - `test_nightly.py`:
    - A stale pending hold → expired.
    - A visitor booking that ended 8 days ago is anonymized; one that ended 6 days ago isn't.
    - Demo rows are untouched by anonymization (they get regenerated).
    - Rate-limit rows older than 1 hour are pruned, and a current-window row stays.
    - Without `ALLOW_DEMO_SEED` there's no reseed; with it, demo rows exist.
    - `seed_demo` without the env var exits non-zero.
- Review constraints: **personal data** (retention and anonymization as stated in `/privacy`: 7 days after the end;
  logs carry counts only); **slot integrity** (claims only through `claim_slots`); **free tier** (one run a day).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Delete non-demo bookings. Real rows are anonymized, never deleted.
- Add Celery, `django.tasks` backends or any scheduler library.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest bookings -q
```
