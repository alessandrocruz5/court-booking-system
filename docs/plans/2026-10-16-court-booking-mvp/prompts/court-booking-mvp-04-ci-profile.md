---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 04
unit: CBS-2
status: done
model: opus
effort: high
depends_on: [02, 03]
parallel_group: D
files:
  create:
    - .github/workflows/ci.yml
    - .github/dependabot.yml
    - CLAUDE.md
    - docs/runbook.md
  modify:
    - README.md
  delete: []
---
# 04 · CI, project profile and docs

## Task
Add GitHub Actions CI (the full verify chain against Postgres 17, plus a gitleaks secrets scan), Dependabot, the
repo's `CLAUDE.md` project profile (exact content below), a `README.md`, and the first `docs/runbook.md` sections.

## Context
- Repo root: `/Users/alessandrocruz/Code/portfolio/court-booking-system`. Prompts 01–03 created the pnpm/Turbo root,
  `apps/backend` (Django 6.1, uv, pytest against Postgres on `localhost:54329`, `compose.yaml` service `db`) and
  `apps/web` (Next.js 16, standalone).
- Reference, **read only**: `/Users/alessandrocruz/Code/fun-run-website/.github/workflows/ci.yml` and `.github/dependabot.yml`.
- **`.github/workflows/ci.yml`**: copy fun-run's structure (name `CI`, `on: pull_request` + `push` to `main`, and the
  same `concurrency` block that never cancels push runs) and change it as follows:
  - Drop the Vercel remote-cache step and every e2e or Playwright step.
  - `verify` job: `permissions: contents: read`. Add a `services.postgres` container: `postgres:17-alpine`, env
    `POSTGRES_USER/PASSWORD/DB = postgres/postgres/cb`, ports `54329:5432`, and health options
    `--health-cmd "pg_isready -U postgres -d cb" --health-interval 2s --health-timeout 3s --health-retries 30`.
  - Steps: `actions/checkout@v7`, `pnpm/action-setup@v6`, `actions/setup-node@v7` (`node-version-file: .nvmrc`,
    `cache: pnpm`), then `astral-sh/setup-uv` at its **current major**. Look it up with
    `gh api repos/astral-sh/setup-uv/releases/latest --jq .tag_name` and use the major tag. Set
    `enable-cache: true` and `cache-dependency-glob: apps/backend/uv.lock`. Then run
    `pnpm install --frozen-lockfile`, `pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test` and `pnpm build`.
    The build step carries the comment "No env: settings and pages read variables per request, never at build time."
  - `secrets` job: copy fun-run's gitleaks job **verbatim**, including the action pinned by SHA
    (`gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e # v3.0.0`), `fetch-depth: 0`, its permissions
    and `GITLEAKS_ENABLE_COMMENTS: "false"`.
- **`.github/dependabot.yml`**: weekly, targeting the default branch (no `target-branch`).
  - `npm` at `/`, with fun-run's minor/patch grouping.
  - `uv` at `/apps/backend`, grouped the same way.
  - `github-actions` at `/`.
- **`CLAUDE.md`**: write exactly the content below. The Jira key is `CBS`. The two `docker build` lines are **not** in `## Commands` yet, because the
  Dockerfiles don't exist until prompt 05, which appends them.

~~~markdown
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
~~~

- **`docs/runbook.md`**: start it with only what is true now. Later prompts append their own sections.
  - `# Runbook`, then a one-paragraph intro (fictional, test mode, where things run).
  - `## Local development`: prerequisites; `corepack enable`; `docker compose up -d --wait db`; backend: copy
    `apps/backend/.env.example` to `.env`, generate `DJANGO_SECRET_KEY` with
    `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`, then `pnpm --filter @cb/backend dev` (port 8000);
    web: copy `apps/web/.env.example` to `.env.local`, then `pnpm --filter @cb/web dev` (port 3000); the full check
    chain (the Commands block).
  - `## Neon (once)`: a project in AWS `ap-southeast-1` with the default Postgres 17, branches `main` (production) and
    `dev`. The owner's **direct** (non-`-pooler`) connection string is kept only on the laptop as `MIGRATE_DATABASE_URL` in `apps/backend/.env`,
    and is never in GitHub or Cloud Run. Free plan limits: 100 CU-hours per month and scale-to-zero after 5 min,
    which is why there are no keep-warm pings.
- **`README.md`**: replace the stub. Cover what it is (fictional, test mode, a portfolio demo for court owners), an
  ASCII architecture sketch (customer → `cb-web` (Next.js) → `cb-backend` `/api/v1` → Neon; staff → `cb-backend`
  `/dashboard` (HTMX); PayMongo → `/webhooks/paymongo`), the stack, a quickstart pointing to the runbook, and
  links to `CLAUDE.md` and `docs/api/`. Keep `LICENSE` as is.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add Docker or deploy jobs. They come in prompts 05–06.
- Add secrets or tokens anywhere, or unpin the gitleaks SHA.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm install --frozen-lockfile && pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && pnpm build
python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/ci.yml','.github/dependabot.yml']]" 2>/dev/null || uvx --from pyyaml python -c "import yaml; [yaml.safe_load(open(f)) for f in ['.github/workflows/ci.yml','.github/dependabot.yml']]"
grep -n '## Commands' CLAUDE.md && grep -n 'gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e' .github/workflows/ci.yml
```
- Optional, if `actionlint` is available: `actionlint .github/workflows/ci.yml` is clean.
