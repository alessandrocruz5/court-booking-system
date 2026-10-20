# CLAUDE.md — Kalaro Courts

## Project

- Jira key: CBS
- Kalaro Courts is a **fictional** sports complex: a portfolio court-booking system. Dummy data and PayMongo test
  mode only, never real payments. Open daily 07:00–23:00 (Asia/Manila); bookings up to 7 days ahead.
  Courts: 2 basketball (full or half; volleyball full only), 4 tennis, 12 badminton/pickleball.
- pnpm + Turborepo monorepo, package scope `@cb/*`:
  - `apps/web` (`@cb/web`): Next.js customer storefront on Cloud Run `cb-web`. Holds no DB credential; calls the
    backend's `/api/v1/*` server-side only, with `INTERNAL_API_TOKEN`.
  - `apps/backend` (`@cb/backend`): Django + HTMX on Cloud Run `cb-backend` (+ job `cb-nightly`). Owns the schema,
    booking rules, PayMongo, the webhook, the storefront API and the staff dashboard. Python via uv; its
    `package.json` is a script shim for Turbo.
  - `packages/config` (`@cb/config`): shared tsconfig, ESLint and Prettier. `packages/env` (`@cb/env`): `createEnv`.
- Neon Postgres (`aws-ap-southeast-1`), Cloud Run `asia-southeast1`, free tier. Operations: [docs/runbook.md](docs/runbook.md).
  API contract: [docs/api/](docs/api/). Plans: [docs/plans/](docs/plans/).

## Workflow

- Base branch: main

## Commands

Run from the repo root, in this order. All must pass before a PR; CI runs the same steps.

```sh
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend
```

Prerequisites: Node 24 with `corepack enable`, uv, Docker. `pnpm test` needs the `db` service (Postgres 17 on
port 54329). `pnpm format` fixes TS/JSON (Prettier) and Python (ruff).

## Review constraints

Each of these is a merge Blocker when violated.

- **The build reads no env.** `next build` and the Docker builds (including `collectstatic`) run with no variables.
  Next reads env per request through `createEnv`; Django settings import cleanly with an empty environment, and
  `validate_runtime_env()` fails fast at gunicorn start.
- **Test mode only.** Only `sk_test_` PayMongo keys are accepted; the webhook rejects `livemode: true`. Every page of
  both apps shows "Fictional venue · Test mode, no real payments".
- **Payment status comes only from the server**: a server-side checkout-session lookup or the signed webhook, both
  through one idempotent `confirm_payment()`. URL parameters are never trusted. The price is quoted on the server,
  snapshotted on the booking and checked against the paid amount.
- **Slot integrity.** Every slot claim goes through `bookings.holds` and relies on the `SlotLock` unique constraint;
  never check-then-insert. No external HTTP call inside a DB transaction.
- **Personal data (RA 10173).** No personal data in logs, error messages, API responses or PayMongo metadata
  (`booking_id` only). Consent is required and timestamped. Visitor bookings are anonymized 7 days after they end.
  `/privacy` must match what is stored and for how long.
- **Database roles.** The backend connects only as `cb_app_login` (member of `cb_app`: DML only). Migrations run as the
  owner from a laptop with `MIGRATE_DATABASE_URL`, which is never set in GitHub or Cloud Run. Expand/contract only; an
  applied migration is never edited.
- **Staff access.** Every dashboard view is wrapped in `@staff_required`; the middleware only redirects. No sign-up,
  no `django.contrib.admin`; accounts come from `manage.py seed_staff` only. Sign-in is rate-limited in the DB. The
  viewer's masking happens in `dashboard/queries.py`, never only in templates; permissions are checked on the server.
- **Internal API.** Every `/api/v1/*` view checks the bearer token in constant time and fails closed. Only Next.js
  server code calls it; the token never reaches a client component; no secret gets a `NEXT_PUBLIC_` prefix.
- **No caching of API responses.** `/api/*` on web and `/api/v1/*` and `/webhooks/*` on the backend send
  `Cache-Control: no-store`.
- **Free tier.** Cloud Run min instances 0, max 1. No keep-warm pings or uptime checks that touch the DB (Neon
  CU-hours).
- **Scope.** Edit only the unit's declared files, and don't refactor adjacent code.

## High-stakes paths

A diff touching any of these gets the code-guardian review before merge, on top of green CI.

- `apps/backend/config/settings.py`
- `apps/backend/*/migrations/**`
- `apps/backend/bookings/models.py`, `apps/backend/bookings/holds.py`
- `apps/backend/payments/**`
- `apps/backend/storefront/auth.py`, `apps/backend/storefront/views.py`
- `apps/backend/accounts/**`
- `apps/backend/core/ratelimit.py`
- `apps/backend/bookings/demo.py`, `apps/backend/bookings/management/**`
- `apps/web/src/lib/api/**`, `apps/web/src/lib/booking/actions.ts`, `apps/web/app/book/success/**`
- `**/Dockerfile`, `.github/workflows/**`

## Hidden coupling

- **Env keys**: `apps/backend/config/env.py` (`REQUIRED_RUNTIME_ENV`) ↔ `apps/*/.env.example` ↔ the CI `images`
  smoke run ↔ `.github/workflows/deploy.yml` (`--set-env-vars`/`--set-secrets`) ↔ Secret Manager ↔ runbook.
- **API contract**: `apps/backend/storefront/{views,payloads}.py` ↔ `docs/api/fixtures/*.json` ↔
  `apps/web/src/lib/api/schemas.ts`. Change all three together; both test suites read the fixtures.
- **Booking rules**: `apps/backend/bookings/{rules,pricing}.py` ↔ `docs/api/fixtures/catalog.json` ↔
  `apps/web/src/content/site.ts` (tested against the fixture).
  `rules.COURT_COUNTS` must match migration `0002_courts` (tested).
- **Grants**: new tables get `cb_app` DML only through `ALTER DEFAULT PRIVILEGES` for the owner role that runs
  migrations (`core/migrations/0002_app_role.py`).
- **Checkout cookie** `cb_checkout` (path `/book`): set in `apps/web/src/lib/booking/actions.ts`, read by
  `app/book/{success,cancelled}`.
- **Demo markers**: `is_demo`, `@example.com`, `+63900000xxxx`, used by `seed_demo`, `nightly` and the dashboard.
- **Cloud names**: region `asia-southeast1`, Artifact Registry `cb`, services `cb-web`/`cb-backend`, job `cb-nightly`.
- **Test DB seed data**: the 18 courts come from migration `bookings/0002_courts`. Django empties every table after
  each `django_db(transaction=True)` test, and pytest-django runs those last, so every transactional test uses
  `serialized_rollback=True`.
