---
type: plan
kind: feature
status: in-progress
repo: court-booking-system
delivery: pr
base: main
sprint: 1
epic: CBS-1
created: 2026-10-16
risk: high
prompts: 24
graph_built: none
tags: [plan]
---
# Court booking MVP: monorepo scaffold to demo-ready

## Request
> we are to create a court booking system for a portfolio. it will just have dummy data but have it be usable and demo-able so that business owners will find it useful. you can analyze the auth dashboard and dockerfile for ~/Code/fun-run-website we can copy how it works to make things easier. customers can book a week in advanced. the complex is open everyday from 7am to 11pm. the court selection is 2 basketball courts (can reserve full or half, can also be used for volleyball but you need to specify), 4 tennis courts. 12 badminton/pickleball courts. we need to create the scaffold for this turbo monorepo. next js, python django + htmx, neon db, free tier cloud run, and paymongo

Clarified with the user on 2026-10-16. **Architecture A**: Django is the core and Next.js is the storefront. **Scope**: the full demo MVP. **Delivery**: PR + Jira (the key is still to come). **Customers**: guest checkout.

| # | Requirement |
|---|---|
| R1 | A pnpm + Turborepo monorepo holding a Next.js app and a Django + HTMX app |
| R2 | Neon Postgres is the database |
| R3 | Both apps run on Cloud Run within the free tier |
| R4 | Payments go through PayMongo, in test mode only, since this is a portfolio with dummy data |
| R5 | Courts: 2 basketball courts, bookable full or half. They can also be used for volleyball, and the sport must be specified. 4 tennis courts. 12 badminton/pickleball courts |
| R6 | The complex is open every day from 07:00 to 23:00 |
| R7 | Customers can book up to one week in advance |
| R8 | Usable and demo-able with dummy data, useful to business owners: a booking flow plus an owner dashboard with live-looking data |
| R9 | Reuse fun-run's auth-dashboard approach. Its "dockerfile" doesn't exist, so new Dockerfiles are written for Cloud Run |
| R10 | Customers book as guests, with no customer accounts (user decision) |

## Context used
- Code: `fun-run-website/apps/admin/src/lib/auth/server.ts:66-119`. Better Auth setup: no sign-up, 12 h sessions, sign-in rate limit of 5 per minute per IP stored in the DB, session IP and user agent nulled, logs redacted.
- Code: `fun-run-website/apps/admin/src/lib/auth/server.ts:128-169`. Sign-in goes through the rate-limited router, never a bare API call.
- Code: `fun-run-website/apps/admin/src/lib/auth/session.ts:13-31`. `requireSession()` runs in the layout and in every page and data function. The proxy only redirects.
- Code: `fun-run-website/apps/admin/src/lib/auth/roles.ts:11-27`. The `owner` and `viewer` roles, and `canSeePersonalData()`.
- Code: `fun-run-website/apps/admin/src/lib/auth/demo-login.ts:11-24`. The demo button posts no fields, and its credentials live only on the server.
- Code: `fun-run-website/apps/admin/app/api/auth/[...all]/route.ts:9-19` (allowlisted auth routes) and `apps/admin/app/login/page.tsx:10-43` (fixed error keys, nothing from the URL rendered).
- Note: `fun-run-website/docs/runbook.md#Organizer dashboard (apps/admin)` (lines 294–399). Accounts come from a seed only, the seed doubles as password rotation, the viewer is masked in the query layer, the demo data has markers (`@example.com`, `+63900000xxxx`), and the reseed is weekly.
- Code: `fun-run-website/packages/payments/src/checkout.ts:12-223`. PayMongo client: test keys only, `metadata` carries the ID only, the checkout URL host is checked, and errors carry status and codes, never bodies.
- Code: `fun-run-website/packages/payments/src/webhook.ts:14-110` (`te`-only HMAC, ±300 s) and `apps/web/app/api/webhooks/paymongo/route.ts:24-84` (401/400/200/500 semantics).
- Code: `fun-run-website/apps/web/src/lib/registration/confirm.ts:173-228`. One idempotent `confirmPayment()` shared by the success page and the webhook. URL parameters are never trusted.
- Code: `fun-run-website/packages/env/src/index.ts:1-33` (`createEnv`, read per request). `packages/db/drizzle/0001_app_role.sql` and `0003_admin_role.sql` (least-privilege NOLOGIN group roles).
- Code: `fun-run-website/apps/web/{proxy.ts,src/lib/csp.ts,next.config.ts,app/api/health/route.ts}`. A CSP nonce per request, static security headers, `/api` set to `no-store`, and a health route with no DB ping.
- Code: `fun-run-website/.github/workflows/ci.yml`. The verify job, plus a gitleaks job pinned by SHA.
- Note: `fun-run-website/CLAUDE.md#Review constraints` and `#High-stakes paths`, ported and adapted here. `TASKS.md` Locked decisions (Sprint 1: portfolio, test mode; Sprint 2: the auth design).
- Search: `git log --all -- '*Dockerfile*'` in fun-run-website returns nothing. The only Dockerfile on this machine is `thelab/lifecert-monorepo/dockerfile` (Go, runs as root, `chmod 777`). It is **not** reused.
- Web: [Cloud Run pricing](https://cloud.google.com/run/pricing). The request-based free tier is 180k vCPU-s, 360k GiB-s and 2M requests a month. Regions are split into Tier 1 and Tier 2. **Singapore (`asia-southeast1`) is Tier 2** (corrected by the audit): the free tier is a spending discount at Tier 1 prices, so it covers about 128k vCPU-s and 257k GiB-s there. Outbound data transfer is free only for 1 GiB a month within North America.
- Web: [Django 6.0 release notes](https://docs.djangoproject.com/en/dev/releases/6.0/): template partials (`partialdef`, `template#partial`), built-in CSP middleware, `django.tasks`. PyPI shows django 6.1.2, psycopg 3.3.6, gunicorn 26.2.0, whitenoise 6.12.0 and django-htmx 1.29.0. npm shows next 16.4.2, turbo 2.11.8 and htmx.org 2.0.11.
- Web: [PayMongo Hosted Checkout](https://developers.paymongo.com/docs/payment-channels-hosted-checkout): v1 and v2 checkout sessions, and the `checkout_session.payment.paid` webhook. [Expire Checkout Session](https://docs.paymongo.com/reference/create_checkout_sessions_id_expire) exists.
- Web: [Neon free plan](https://neon.com/faqs/free-plan-limits-and-quotas): 100 CU-hours per project per month, scale-to-zero after 5 min that can't be turned off, and 0.5–1 GB of storage.
- Local toolchain: node 26.11, corepack 0.36, uv 0.13.0, docker 29.8, psql 18.6 and gh 2.102 are installed. **Missing**: pnpm (use corepack), gcloud, neonctl and ruff (comes in through uv).
- Graph: none, since the repo is greenfield with only `README.md` and `LICENSE`.

## Options
| Option | Cost | Time | Risk | Maintenance | Compliance |
|---|---|---|---|---|---|
| **A. Django core, Next.js storefront.** Django owns the DB, the rules, PayMongo, the webhook and the HTMX staff dashboard. Next.js is the customer site and calls Django server-to-server | 2 Cloud Run services + 1 job, all free tier | Medium | Cold visits chain two services plus Neon | One schema owner, one auth stack, one payment implementation | Next.js holds no DB credential, and personal data stays in one place |
| C. Django + HTMX storefront, Next.js dashboard copied from fun-run (Better Auth + Drizzle) | Same | Lower at first, because it copies more code | Two migration tools on one DB | Two auth stacks and two ORMs drift | DB credentials in both apps |
| E. Django does everything, and Next.js is a static landing page | Cheapest | Lowest | Lowest | Lowest | Same as A |

**Recommendation:** A. Each framework does what it does best, there's one system of record, and fun-run's auth *design* ports cleanly onto `django.contrib.auth`. **Chosen:** A (user, 2026-10-16).

## Decisions
- **Layout.** `apps/web` (`@cb/web`, Next.js 16.4, Cloud Run `cb-web`) and `apps/backend` (`@cb/backend`, Django 6.1 on Python 3.14 with uv, Cloud Run `cb-backend` plus job `cb-nightly`). `packages/config` and `packages/env` are copied from fun-run (`@rr` → `@cb`). There's no shared UI package, because only one JS app exists. `apps/backend/package.json` is a script shim so Turbo runs ruff and pytest.
- **One system of record.** Django owns the schema and migrations. Next.js never touches the DB: it calls `/api/v1/*` on Django from the server only, with `Authorization: Bearer $INTERNAL_API_TOKEN` compared in constant time. The webhook and the dashboard live on Django.
- **The API contract is pinned by fixtures** in `docs/api/fixtures/*.json`. Django's tests assert their responses have the same shape (and the catalog matches exactly), and Next.js's tests zod-parse every fixture.
- **Slots.** Bookings start on the hour, last 1–3 hours, and run 07:00–23:00, so the last start is 22:00. Dates run from today to today + 6, 7 dates in all, in Asia/Manila. Only start times in the future can be booked. Constants live in `bookings/rules.py`.
- **Conflicts are prevented by the database.** There's one `SlotLock` row per court, space and hour, with a `UNIQUE(court, space, starts_at)` constraint. Basketball courts have spaces `A` and `B`, and a full-court booking locks both. Every other court has one space, `F`. There's no check-then-insert without the constraint, and Postgres has no extension to install.
- **Sports.** A sport is required on every booking. Basketball courts take basketball (full or half) or volleyball (**full court only**). Tennis courts take tennis. Courts 1–12 take badminton or pickleball. A half-court booking gets whichever half is free, A first.
- **Holds** last 20 minutes while payment is pending. They expire lazily, inside the next claim on those slots, and in the nightly job. A payment that lands after its hold was reclaimed tries to get its slots back; if they're taken, the booking becomes `needs_refund` and is flagged on the dashboard.
- **Prices** are dummy figures in centavos per hour, off-peak / peak. Peak is weekdays from 17:00 and all day on weekends. Basketball full ₱1,200/₱1,600, half ₱700/₱900. Volleyball ₱1,200/₱1,600. Tennis ₱500/₱700. Badminton ₱350/₱450. Pickleball ₱400/₱500. The server quotes the price and snapshots it on the booking, and the paid amount is checked against the snapshot.
- **PayMongo** uses `/v1/checkout_sessions`, which is proven end to end in fun-run on this account. The methods are `card`, `gcash`, `paymaya` and `grab_pay`. Metadata carries only `booking_id`. Only `sk_test_` keys are accepted, and the webhook verifies the `te` signature and rejects `livemode`. A cancelled checkout expires the PayMongo session.
- **Staff auth** ports fun-run's design onto `django.contrib.auth`. Groups are `owner` (full data) and `viewer` (the demo: personal data masked in the query layer). There's no sign-up and no `django.contrib.admin`; accounts come only from `manage.py seed_staff`. Sign-in is limited to 5 per minute per IP, with the counts in the DB. The "Explore the owner demo" button posts no fields. Sessions last 12 h. `@staff_required` guards every view, and the middleware only redirects.
- **The viewer can operate the demo.** It can add walk-ins and blocks (today to today + 6 only), and cancel demo or staff-made bookings, up to 20 writes per 10 minutes per IP. Only the owner can cancel a real visitor's online booking. The nightly reseed restores the demo state. A `needs_refund` booking is refunded by hand in the PayMongo test dashboard and stays flagged as an audit trail.
- **Rate limits** live in one DB table, `core_ratelimit`. Keys are an HMAC of the IP, never the raw address. Booking holds are limited to 5 per 10 minutes per IP and 2 active holds per email, lookups to 10 per 10 minutes per IP, staff sign-in to 5 per minute per IP, and the viewer's dashboard writes to 20 per 10 minutes per IP. The client IP is the rightmost `X-Forwarded-For` entry, which Cloud Run's front end appends; this is verified at deploy (see Known risks).
- **No email or SMS.** The success page shows the reference, and `/booking` looks it up by reference plus email.
- **Personal data (RA 10173).** The app stores name, email and mobile, with consent and a timestamp. Visitor bookings are anonymized by the nightly run once 7 days have passed since they end (so within 8 days), and rate-limit rows are deleted within a day. There's no personal data in the app's logs, PayMongo metadata or API responses: logged exceptions keep their stack but show only the class and SQLSTATE (`core.logging.RedactingFormatter`), because psycopg's message quotes the failing row. Gunicorn's access log keeps the path only, with no query string and no IP. Cloud Run's **platform** request logs do record the IP and URL (30-day default retention). `/privacy` discloses this and matches all of the above.
- **Demo data.** `seed_demo` regenerates `is_demo` bookings from today − 30 to today + 6 using `@example.com` emails and `+63900000xxxx` mobiles. It respects real bookings and is deterministic per day. `nightly`, a Cloud Run Job triggered by Cloud Scheduler at 03:00 Manila time, expires holds, anonymizes, prunes, clears sessions and reseeds.
- **Cloud Run.** Region `asia-southeast1`, next to Neon's `aws-ap-southeast-1`. Instances run min 0 / **max 1** (user, 2026-10-16: one instance per service is plenty for a demo and halves the worst case under a traffic flood) with 1 vCPU, 512 Mi, request-based billing and CPU boost. Expected bill: $0 compute; at most a few cents of outbound data transfer (pages to visitors, queries to Neon on AWS), which no region's free tier covers outside North America. GitHub Actions builds the images and deploys through Workload Identity Federation, with no JSON keys. **Six** Secret Manager secrets, which is exactly the free cap. Artifact Registry keeps the 2 newest images. A $1 budget alert is set. There are no keep-warm pings, because they would burn Neon's 100 CU-hours.
- **Database roles.** The runtime connects only as `cb_app_login` (a member of `cb_app`, which has DML only and can't touch `django_migrations`). Migrations run from a laptop as the owner using `MIGRATE_DATABASE_URL`, which is never in GitHub or Cloud Run. Migrations are expand/contract only.
- **Neon pooler.** `CONN_MAX_AGE=0`, `DISABLE_SERVER_SIDE_CURSORS=True`, and psycopg's default client-side binding, so there are no prepared statements.
- **Tests** run against Postgres 17: Docker Compose on port 54329 locally, a service container in CI. SQLite is not used, because the constraints and concurrency tests need Postgres. Every `django_db(transaction=True)` test also sets `serialized_rollback=True`: Django empties all tables after each transactional test and pytest-django runs them last, so the migration-seeded courts would otherwise vanish for the next one.
- **Audit mitigations (2026-10-16).** The catalog reads `rules.COURT_COUNTS` and never queries the DB, so landing-page visits don't wake Neon, and `robots.ts` disallows `/book`, `/booking` and `/staff`. `/book` has a `loading.tsx` skeleton, so a cold backend can't block the page. Turbo's `test` inputs include `docs/api/fixtures/**`. Ops steps ship with the unit that needs them: DB roles and migrations in CBS-4 (08), PayMongo keys and the webhook in CBS-5 (11). Backend 404/500 pages carry the banner. Dashboard toasts are htmx out-of-band swaps, not `HX-Trigger`. Ruff's DJ001 is silenced per field with a reason, never by dropping `null=True`. Units merge strictly in order CBS-2→CBS-10.
- **Fictional brand.** The venue is "Kalaro Courts", a fictional name that appears in one constant per app. Every page shows "Fictional venue · Test mode, no real payments".

**Non-goals:** customer accounts, self-service cancel or reschedule, refunds through the API, email and SMS, a captcha or Turnstile (rate limits stand in), recurring bookings and memberships, promo codes, holiday pricing, multiple venues, Filipino localisation, `django.contrib.admin`, Python type checking (mypy/pyright), Playwright e2e (a follow-up hardening sprint), a custom domain, live PayMongo, a shared UI package and a Postman collection.

## Change list
| File | Action | Why | Req | Prompt |
|---|---|---|---|---|
| `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `.nvmrc`, `.npmrc`, `.editorconfig`, `.gitignore`, `eslint.config.mjs`, `pnpm-lock.yaml` | C | Monorepo root, copied from fun-run | R1 | 01 |
| `packages/config/**`, `packages/env/**` | C | Shared lint, format and tsconfig, plus `createEnv` | R1 | 01 |
| `apps/backend/{package.json,pyproject.toml,uv.lock,.python-version,manage.py,.env.example,conftest.py}` | C | Django workspace, wired into Turbo | R1 | 02 |
| `apps/backend/config/{__init__,env,settings,settings_test,urls,wsgi,gunicorn.conf}.py` | C | Settings that are Neon-safe, Cloud Run-safe and readable with no env at build | R1 R2 R3 | 02 |
| `apps/backend/core/{__init__,apps,views,logging}.py`, `core/tests/{__init__,test_health,test_env,test_logging}.py` | C | `/healthz` (no DB), env validation, exception redaction in logs | R3 | 02 |
| `compose.yaml` | C | Local and test Postgres 17 | R2 | 02 |
| `turbo.json`, root `package.json` | M | Env passthrough; `format` also runs ruff | R1 | 02 |
| `apps/web/{package.json,next.config.ts,tsconfig.json,eslint.config.js,postcss.config.mjs,vitest.config.ts,.env.example,proxy.ts}` | C | Next.js storefront shell, standalone output | R1 R3 | 03 |
| `apps/web/app/{layout,page,error,global-error,not-found}.tsx`, `app/{globals.css,robots.ts,icon.svg,api/health/route.ts,__tests__/error.test.tsx}`, `apps/web/public/.gitkeep` | C | Shell pages, banner, health route | R1 R8 | 03 |
| `apps/web/src/{content/site.ts,components/test-mode-banner.tsx,lib/csp.ts,lib/__tests__/csp.test.ts}` | C | Brand constants, test-mode banner, CSP | R8 | 03 |
| `.github/workflows/ci.yml`, `.github/dependabot.yml` | C | CI with Postgres and uv, plus gitleaks | R1 | 04 |
| `CLAUDE.md`, `docs/runbook.md` | C | Project profile and operations | R1 | 04 |
| `README.md` | M | Project overview | R8 | 04 |
| `apps/web/Dockerfile`, `apps/backend/Dockerfile`, `.dockerignore`, `apps/backend/.dockerignore` | C | Images for Cloud Run: non-root, no env at build | R3 R9 | 05 |
| `.github/workflows/ci.yml`, `.github/dependabot.yml`, `CLAUDE.md` | M | `images` job with a smoke run; Docker updates; the two `docker build` lines added to `## Commands` (not before the Dockerfiles exist) | R3 | 05 |
| `.github/workflows/deploy.yml` | C | WIF to Artifact Registry, then Cloud Run services and the job | R3 | 06 |
| `docs/runbook.md` | M | GCP setup, secrets, free-tier guardrails, rollback | R3 | 06 |
| `apps/backend/bookings/{__init__,apps,models,rules}.py`, `bookings/migrations/{__init__,0001_initial,0002_courts}.py`, `bookings/tests/{__init__,test_models}.py` | C | Courts, Booking, SlotLock, and the 18 courts | R5 | 07 |
| `apps/backend/config/settings.py` | M | Install `bookings` | R5 | 07 |
| `apps/backend/core/{models,ratelimit}.py`, `core/migrations/{__init__,0001_ratelimit,0002_app_role}.py`, `core/tests/{test_ratelimit,test_grants}.py` | C | DB rate limiter; least-privilege `cb_app` | R2 R9 | 08 |
| `docs/runbook.md` | M | Database roles and migrations (needed before CBS-6/CBS-7 deploy) | R2 | 08 |
| `apps/backend/bookings/{pricing,availability,holds,references}.py`, `bookings/tests/{test_rules,test_pricing,test_availability,test_holds}.py` | C | Rules, quotes, availability, holds, conflicts | R5 R6 R7 | 09 |
| `apps/backend/bookings/rules.py` | M | Validation functions | R5 R6 R7 | 09 |
| `apps/backend/payments/{__init__,apps,env,paymongo,webhook}.py`, `payments/tests/{__init__,test_env,test_paymongo,test_webhook_signature}.py` | C | PayMongo client ported from fun-run | R4 | 10 |
| `apps/backend/pyproject.toml`, `uv.lock`, `config/settings.py`, `.env.example` | M | httpx; install `payments`; PayMongo keys in the template | R4 | 10 |
| `apps/backend/payments/{confirm,views,urls}.py`, `payments/tests/{test_confirm,test_webhook_view}.py` | C | Idempotent confirm, signed webhook | R4 | 11 |
| `apps/backend/config/urls.py`, `docs/runbook.md` | M | Mount `/webhooks/`; PayMongo test keys and webhook registration | R4 | 11 |
| `apps/backend/storefront/{__init__,apps,auth,payloads,views,urls}.py`, `storefront/tests/{__init__,test_auth,test_catalog_availability,test_contract}.py` | C | Token-guarded catalog and availability API | R5 R6 R7 | 12 |
| `docs/api/README.md`, `docs/api/fixtures/{catalog,availability,error}.json` | C | Contract | R1 | 12 |
| `apps/backend/config/{settings,urls}.py`, `apps/backend/.env.example`, `turbo.json` | M | Install `storefront`, mount `/api/v1/`, token; fixtures as `test` inputs | R1 | 12 |
| `apps/backend/storefront/{views,payloads,urls}.py`, `storefront/tests/test_contract.py`, `docs/api/README.md` | M | Booking, checkout and lookup endpoints | R4 R10 | 13 |
| `apps/backend/storefront/tests/{test_bookings_api,test_checkout_api}.py`, `docs/api/fixtures/{booking-created,checkout-status,checkout-release,booking-lookup}.json` | C | Tests and contract | R4 R10 | 13 |
| `apps/web/src/lib/api/{env,client,schemas}.ts`, `src/lib/api/__tests__/{schemas,client}.test.ts`, `src/test/server-only-stub.ts` | C | Typed, server-only API client | R1 | 14 |
| `apps/web/{package.json,vitest.config.ts,.env.example}` | M | zod and server-only; test alias; API env | R1 | 14 |
| `apps/web/app/book/{page,loading}.tsx`, `src/lib/booking/{params.ts,__tests__/params.test.ts}`, `src/components/booking/{sport-picker,duration-picker,date-strip,availability-grid}.tsx` | C | Sport → duration → date → court and time | R5 R6 R7 | 15 |
| `apps/web/src/lib/booking/{actions.ts,__tests__/actions.test.ts}`, `src/components/booking/details-form.tsx`, `app/book/{success,cancelled}/page.tsx` | C | Guest details → PayMongo → result | R4 R10 | 16 |
| `apps/web/app/book/page.tsx` | M | Details step | R4 | 16 |
| `apps/web/app/{page.tsx,booking/page.tsx,privacy/page.tsx,staff/route.ts}`, `src/lib/booking/lookup.ts`, `src/components/booking/lookup-form.tsx`, `src/content/{site.ts,__tests__/site.test.ts}`, `apps/web/.env.example` | C/M | Landing, lookup, privacy notice, link to the owner demo | R8 R10 | 17 |
| `apps/backend/bookings/demo.py`, `bookings/management/{__init__,commands/__init__,commands/seed_demo,commands/nightly}.py`, `bookings/tests/{test_demo,test_nightly}.py` | C | Live-looking demo data; retention | R8 | 18 |
| `docs/runbook.md`, `apps/backend/.env.example` | M | Demo data and Scheduler; `ALLOW_DEMO_SEED` in the template | R8 | 18 |
| `apps/backend/accounts/{__init__,apps,roles,decorators,middleware}.py`, `accounts/management/{__init__,commands/__init__,commands/seed_staff}.py`, `core/http.py`, `accounts/tests/{__init__,test_access,test_seed_staff}.py` | C | Roles, seeded accounts, access checks | R9 | 19 |
| `apps/backend/config/settings.py`, `apps/backend/.env.example` | M | Install `accounts`, middleware, login URL; staff and demo keys in the template | R9 | 19 |
| `apps/backend/accounts/{views,urls}.py`, `accounts/templates/accounts/login.html`, `templates/{base,404,500}.html`, `core/static/core/base.css`, `accounts/tests/test_login.py` | C | Sign-in, demo button, sign-out; shared layout and tokens; error pages with the banner | R9 | 20 |
| `apps/backend/config/urls.py`, `docs/runbook.md` | M | Mount `/dashboard/` auth; staff ops | R9 | 20 |
| `apps/backend/dashboard/{__init__,apps,urls,views,queries}.py`, `dashboard/templates/dashboard/{base,overview}.html`, `dashboard/static/dashboard/{dashboard.css,htmx.min.js}`, `dashboard/tests/{__init__,test_overview}.py` | C | HTMX shell (htmx 2.0.11 vendored from the npm tarball, no CDN) and owner KPIs | R8 | 21 |
| `apps/backend/config/{settings,urls}.py` | M | Install `dashboard`; `/` → `/dashboard/`. No django-htmx: the `HX-Request` header plus built-in partials are enough | R8 | 21 |
| `apps/backend/dashboard/{schedule,forms}.py`, `dashboard/templates/dashboard/schedule.html`, `dashboard/tests/test_schedule.py` | C | Day grid, walk-ins, blocks, cancels | R5 R8 | 22 |
| `apps/backend/dashboard/{views,urls}.py`, `dashboard/templates/dashboard/base.html`, `dashboard/static/dashboard/dashboard.css`, `bookings/holds.py` | M | Wire the schedule, add the nav item and slot styles; `cancel_booking` | R8 | 22 |
| `apps/backend/dashboard/templates/dashboard/{bookings,booking_detail}.html`, `dashboard/tests/test_bookings.py` | C | Search, filters, detail, masking | R8 R9 | 23 |
| `apps/backend/dashboard/{views,urls,queries}.py`, `dashboard/templates/dashboard/base.html` | M | Wire the list and detail; nav item | R8 | 23 |
| `docs/runbook.md`, `README.md` | M | Pre-release checklist, demo script | R8 | 24 |

## Blast radius
**Risk:** high. The work is greenfield, but it carries payments, staff auth, personal data, migrations with DB roles, concurrency, and CI/CD that holds cloud credentials.

There is no existing code, so nothing in this repo can break. The radius is the coupling that **this plan creates between its own units**, plus the external systems:

| Affected | Kind | Via | Breaks? | Mitigation |
|---|---|---|---|---|
| `apps/web/src/lib/api/schemas.ts` ↔ `storefront/views.py` | Non-graph (JSON contract) | `/api/v1/*` field names and status codes | Yes, on drift | Shared `docs/api/fixtures/*.json`, checked by both suites (12, 13, 14). Catalog equality is exact |
| Env inventory: `config/env.py REQUIRED_RUNTIME_ENV`, `.env.example` files, CI smoke env (05), `deploy.yml` (06), Secret Manager | Non-graph (env keys) | Key names | Yes, if a later prompt adds a required key | Prompt 02 declares **every** required key in this plan up front. PayMongo and demo keys are validated per use, so prompts after 06 never touch CI or deploy. The prompts that read per-use keys (10, 18, 19) add them to `apps/backend/.env.example` (audit) |
| `core/migrations/0002_app_role.py` → every later table | Non-graph (grants) | `ALTER DEFAULT PRIVILEGES` for the migrating owner | Only if a non-owner runs migrations | The runbook and review constraints say migrations run as the owner only. `test_grants.py` asserts DML works, DDL is denied and `django_migrations` writes are denied |
| `bookings/holds.py` (`claim_slots`, `release`, `reacquire`) → payments (11), storefront (13), demo (18), schedule (22) | Direct | Function calls | Yes, if signatures change | Signatures are fixed in 09's prompt and repeated in each consumer's prompt. The concurrency test lives with the definition |
| `bookings/rules.py` constants → catalog fixture → `src/content/site.ts` | Non-graph | 07:00/23:00, 7 days, 3 h | Copy drifts | `site.test.ts` reads `catalog.json`, and Django's catalog test matches it exactly |
| Cookie `cb_checkout` (16 sets it, 16 reads it) | Non-graph | Cookie name and path `/book` | Low | One constant in `actions.ts` |
| PayMongo test account | External | Allowed methods, webhook URL and secret | Methods may differ per account | The methods list matches fun-run's, which is proven on this account. CBS-5's prompt 11 writes `## PayMongo (test mode)`: test keys, webhook registration through `POST /v1/webhooks`, secret storage |
| Neon project | External | `cb_app_login`; 100 CU-h a month | Suspends if overused | No keep-warm. Nightly is the only scheduled DB use |
| GCP billing | External | Free tier (Singapore is Tier 2) | Cents possible: outbound data transfer outside North America, Artifact Registry over 0.5 GB | Cleanup policy keeps 2 images, $1 budget alert (it emails, it doesn't stop spending), max 1 instance per service |
| Test DB seed data | Non-graph (test isolation) | Django flushes all tables after each `transaction=True` test; pytest-django runs those last | Yes: later transactional tests lose the 18 courts (audit BLOCK) | Every transactional test sets `serialized_rollback=True` (08, 09, 11); `CLAUDE.md` Hidden coupling says so for future prompts |
| `turbo.json` `test` cache ↔ `docs/api/fixtures/**` | Non-graph (build cache) | Fixtures sit outside both packages | Yes, locally: a fixture edit replays a cached green test | 12 adds the fixtures to the `test` task's `inputs` |
| `fun-run-website` | Read-only source | Prompts copy from it | No | Never modified |
| `turbo.json` strict env mode → `@cb/backend` scripts | Non-graph | `uv` needs `HOME` and cache variables | Possible | Prompt 02 verifies through `pnpm test` and adds `globalPassThroughEnv` as needed |

**Known risks in the touched area:**
1. **Cold-start chain.** A first visit can wait on Next.js, then Django, then Neon, about 3–6 s. Mitigations: Suspense streaming on `/`, a `loading.tsx` skeleton on `/book` (its page awaits the catalog first), a DB-free catalog, CPU boost and slim images. Keep-warm pings are not a mitigation, because of the Neon quota.
2. **Late payments.** A payment that arrives after its hold expired and the slot was re-booked becomes `needs_refund`. The dashboard flags it and the runbook covers the manual test-mode refund. Cancelling a checkout expires the PayMongo session to shrink the window.
3. **`X-Forwarded-For` on Cloud Run.** The plan assumes the rightmost entry is the address Google's front end saw. This is unverified, so the runbook check in 24 sends a forged header and confirms the rate limit still applies, then signs in from a second network to prove the rightmost entry is per client rather than a shared front-end address (the same for the web lookup).
4. **New APIs.** Django 6.1's CSP and template partials and Next 16.4's `proxy.ts` behave differently from older versions. The prompts tell the executor to read the installed sources or docs first.
5. **The Secret Manager free tier is 6 active versions**, and this plan uses exactly 6. Disable old versions after a rotation.
6. **Personal data.** The runtime and logs must stay free of personal data. The constraint and the per-prompt tests cover this, and `core.logging.RedactingFormatter` keeps psycopg's failing-row text out of Django's 500 logs.
7. **The public demo account.** Anyone can click "Explore the owner demo" and write as the viewer. Writes are limited to 20 per 10 minutes per IP and to today + 6, and the nightly reseed removes them.

## Units
| Unit | Title | Category | Prompts | Depends | High-stakes | Acceptance criteria |
|---|---|---|---|---|---|---|
| CBS-2 | Monorepo scaffold, CI and project profile | Added | 01, 02, 03, 04 | — | yes | R1: `pnpm install/lint/typecheck/test/build` pass at the root across `@cb/web`, `@cb/backend`, `@cb/env`. Django `/healthz` and Next `/api/health` answer 200 `no-store`. The banner shows on every page. CI is green with Postgres and gitleaks. |
| CBS-3 | Container images and Cloud Run deploy | Added | 05, 06 | CBS-2 | yes | R3: both images build with no env and run as non-root. The CI smoke run hits both health routes. `deploy.yml` deploys `cb-web` and `cb-backend` (min 0 / max 1) and the job `cb-nightly` through WIF, and it is skipped until the GCP variables exist. |
| CBS-4 | Booking engine: courts, rules, holds | Added | 07, 08, 09 | CBS-3 | yes | R5–R7: the 18 courts are seeded. Half/full/volleyball/sport rules, 07:00–23:00, a 7-day window and 1–3 h are enforced. Concurrent overlapping holds produce exactly one winner. `cb_app` can't run DDL. |
| CBS-5 | PayMongo payments | Added | 10, 11 | CBS-4 | yes | R4: only test keys are accepted. The webhook verifies the signature before any DB access. Confirmation is idempotent and amount-checked. A late payment is reacquired or becomes `needs_refund`. |
| CBS-6 | Storefront API | Added | 12, 13 | CBS-5 | yes | R4–R7, R10: the token-guarded endpoints catalog, availability, booking (hold + checkout), confirm, release and lookup exist, with rate limits. Responses match `docs/api/fixtures`. |
| CBS-7 | Customer booking site | Added | 14, 15, 16, 17 | CBS-6 | yes | R4–R8, R10: a guest can pick sport, duration, date and time, enter details, pay in PayMongo test mode, and see a confirmed reference. Lookup works. The landing page, privacy page and banner are in place. |
| CBS-8 | Demo data and nightly job | Added | 18 | CBS-7 | yes | R8: `seed_demo` fills 37 days with realistic, deterministic data that respects real bookings. `nightly` expires holds, anonymizes visitor data after 7 days, prunes and reseeds. |
| CBS-9 | Staff sign-in and dashboard overview | Added | 19, 20, 21 | CBS-8 | yes | R8, R9: seeded owner and viewer only, a demo button with no fields posted, 5 sign-ins per minute per IP, `@staff_required` everywhere. The overview shows KPIs, revenue by sport, a utilization heatmap and `needs_refund` alerts. |
| CBS-10 | Dashboard operations | Added | 22, 23, 24 | CBS-9 | yes | R5, R8: the day schedule grid (with halves) supports walk-ins, blocks and cancels, with permissions enforced on the server. The bookings list has search, filters and masked detail. The runbook's pre-release checklist exists. |

Merge order, strictly linear: CBS-2 → CBS-3 → CBS-4 → CBS-5 → CBS-6 → CBS-7 → CBS-8 → CBS-9 → CBS-10. Each unit branches from `main` after the previous one merges. CBS-5, CBS-6 and CBS-9 all edit the high-stakes `config/settings.py` and `config/urls.py`, and CBS-8 and CBS-9 both append to the runbook, so parallel branches would conflict and leave each prompt's "already there" context stale (audit). `/staff` on the storefront returns 404 between the CBS-7 and CBS-9 deploys; nobody sees it before CBS-10's pre-release checklist.

## Prompts
| # | Title | Unit | Model | Effort | Depends | Group | Files |
|---|---|---|---|---|---|---|---|
| 01 | Root workspace and shared TS packages | CBS-2 | sonnet | medium | — | A | root config, `packages/{config,env}/**` |
| 02 | Django backend skeleton | CBS-2 | opus | high | 01 | B | `apps/backend/**` skeleton, `compose.yaml`, `turbo.json` |
| 03 | Next.js storefront skeleton | CBS-2 | sonnet | medium | 01 | C | `apps/web/**` shell |
| 04 | CI, project profile and docs | CBS-2 | opus | high | 02, 03 | D | `.github/**`, `CLAUDE.md`, `README.md`, `docs/runbook.md` |
| 05 | Container images | CBS-3 | opus | high | 04 | E | `apps/*/Dockerfile`, `.dockerignore`s, `ci.yml`, `dependabot.yml` |
| 06 | Cloud Run deploy pipeline | CBS-3 | opus | high | 05 | F | `.github/workflows/deploy.yml`, `docs/runbook.md` |
| 07 | Booking schema and courts | CBS-4 | opus | xhigh | 06 | G | `apps/backend/bookings/{models,rules}.py`, migrations |
| 08 | Rate limiter and least-privilege role | CBS-4 | opus | high | 07 | H | `apps/backend/core/{models,ratelimit}.py`, migrations, `docs/runbook.md` |
| 09 | Rules, pricing, availability and holds | CBS-4 | opus | xhigh | 08 | I | `apps/backend/bookings/{rules,pricing,availability,holds,references}.py` |
| 10 | PayMongo client and webhook signature | CBS-5 | opus | high | 09 | J | `apps/backend/payments/{env,paymongo,webhook}.py` |
| 11 | Payment confirmation and webhook endpoint | CBS-5 | opus | xhigh | 10 | K | `apps/backend/payments/{confirm,views,urls}.py`, `docs/runbook.md` |
| 12 | Storefront API: auth, catalog, availability | CBS-6 | opus | high | 11 | L | `apps/backend/storefront/**`, `docs/api/**`, `turbo.json` |
| 13 | Storefront API: bookings, checkout, lookup | CBS-6 | opus | xhigh | 12 | M | `apps/backend/storefront/**`, `docs/api/fixtures/*` |
| 14 | Web API client | CBS-7 | opus | high | 13 | N | `apps/web/src/lib/api/**` |
| 15 | Booking browse flow | CBS-7 | sonnet | high | 14 | O | `apps/web/app/book/{page,loading}.tsx`, `src/components/booking/*` |
| 16 | Checkout, success and cancelled | CBS-7 | opus | high | 15 | P | `apps/web/src/lib/booking/actions.ts`, `app/book/{success,cancelled}` |
| 17 | Landing, lookup, privacy, staff link | CBS-7 | sonnet | high | 16 | Q | `apps/web/app/{page,booking,privacy,staff}` |
| 18 | Demo data and nightly job | CBS-8 | opus | high | 17 | R | `apps/backend/bookings/{demo.py,management/**}` |
| 19 | Staff roles, seeded accounts and access checks | CBS-9 | opus | xhigh | 18 | S | `apps/backend/accounts/**`, `core/http.py` |
| 20 | Staff sign-in, demo button and sign-out | CBS-9 | opus | high | 19 | T | `apps/backend/accounts/{views,urls}.py`, templates |
| 21 | Dashboard shell and overview | CBS-9 | sonnet | high | 20 | U | `apps/backend/dashboard/**` |
| 22 | Schedule grid: walk-ins, blocks, cancels | CBS-10 | opus | high | 21, 18 | V | `apps/backend/dashboard/{schedule,forms}.py`, `bookings/holds.py` |
| 23 | Bookings list and detail | CBS-10 | sonnet | high | 22 | W | `apps/backend/dashboard/**` |
| 24 | Pre-release checklist and demo guide | CBS-10 | haiku | low | 23 | X | `docs/runbook.md`, `README.md` |

No prompts run in parallel. Every prompt that adds a dependency touches `pnpm-lock.yaml` or `uv.lock`, and units are sequential PRs.

Why each `opus` prompt needs opus:
- 02: `config/settings.py` holds every security setting (proxy SSL, cookies, CSP, hosts) and the Neon pooler flags.
- 04: workflow permissions and the gitleaks pin. `.github/workflows/**` is high-stakes.
- 05: the Dockerfiles must build with no env, run as non-root and handle a monorepo prune. High-stakes.
- 06: the deploy workflow holds cloud credentials (WIF), the secret wiring and the free-tier flags.
- 07: the schema's constraints carry the integrity guarantees, and migrations are high-stakes.
- 08: a role and grants migration with cluster-level effects, plus an atomic upsert.
- 09: concurrency and slot integrity, the core correctness guarantee.
- 10: payments and secret validation.
- 11: idempotent money state transitions under races, and the webhook trust boundary.
- 12: the trust boundary between services.
- 13: payment orchestration across the DB and PayMongo, rate limits and personal data.
- 14: server-only token handling and the client-IP trust rule, on the high-stakes `apps/web/src/lib/api/**` (audit).
- 16: payment status shown to customers, and the secret-bearing server action.
- 18: deletes and anonymizes production rows under RA 10173 (audit).
- 19: access control and account seeding.
- 20: sign-in, rate limiting and demo credentials.
- 22: staff writes through the slot engine, with permission enforcement.

## End-to-end verification
```bash
# CLAUDE.md ## Commands (created by prompt 04), from the repo root, in order:
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend

# R1: both apps run under Turbo
pnpm turbo run lint --dry=json | grep -E '"@cb/(web|backend)#lint"'

# R5 R6 R7: rules, conflicts and window (Postgres up)
(cd apps/backend && uv run pytest bookings -q)
# R4: payments
(cd apps/backend && uv run pytest payments storefront -q)
# R9: access control, sign-in rate limit, masking
(cd apps/backend && uv run pytest accounts dashboard -q)
# R2: least privilege
(cd apps/backend && uv run pytest core/tests/test_grants.py -q)

# R3 (after the owner setup in the runbook): Actions → Deploy is green, then
curl -fsS "$BACKEND_URL/healthz" && curl -fsS "$WEB_URL/api/health"
gcloud run services describe cb-web --region asia-southeast1 --format='value(spec.template.metadata.annotations)' | grep -E 'maxScale.: .1'
# R4 R8 R10 (manual, test mode): book a tennis court on $WEB_URL with test card 4343 4343 4343 4345,
#   see the confirmed reference, look it up on /booking, open /staff → "Explore the owner demo",
#   find the booking on the schedule. Every page shows "Fictional venue · Test mode, no real payments".
```

## Rollback
- Per unit: revert the PR on `main`. The deploy workflow redeploys the previous commit's images, or run `gcloud run services update-traffic <svc> --to-revisions <rev>=100`.
- Migrations in this plan only add things. Rolling back code never needs a schema rollback. If it did, use Neon point-in-time restore on a branch within the free plan's history window. Never edit an applied migration.
- Secrets: disable the new version in Secret Manager and redeploy.

## Log
- 2026-10-16: planned. Architecture A, full MVP, PR delivery (Jira key pending), guest checkout.
- 2026-10-16: tickets created: Epic CBS-1, units CBS-2…CBS-10 (U1…U9). CBS-4 now depends on CBS-3, to match the linear merge order.
- 2026-10-16: audited, 20 fixes applied (1 BLOCK, 19 FIX) plus 6 of 7 notes (`@cb/env` kept for fun-run parity). User decision: Cloud Run max instances 2 → 1.
- 2026-10-17: CBS-2 build started on branch CBS-2. Rollback point: 3b62227909207a9266f8c6bafb366b366961a80a.
- 2026-10-17: 01 done (sonnet, 0 retries): root workspace, @cb/config and @cb/env copied from fun-run; turbo needs a real pnpm on PATH (corepack enable --install-directory).
- 2026-10-17: 02 done (opus, 0 retries): Django 6.1.2 / Python 3.14 skeleton, 21 tests; turbo.json gained globalPassThroughEnv TEST_DATABASE_URL (strict mode dropped it); check --deploy has 3 expected warnings (W005/W021 HSTS by design, W008 test settings).
- 2026-10-17: 03 done (sonnet, 0 retries): Next 16 storefront shell, standalone, no-env build; 13 web tests. One-off vitest ENOTEMPTY on node_modules/.vitest-cache when turbo ran two vitest tasks in parallel (not reproduced in 6 cold runs).
- 2026-10-17: 04 done (opus, 0 retries): CI (verify + gitleaks), dependabot, CLAUDE.md (verbatim), runbook, README. Deviations: setup-uv pinned by SHA (# v10.3.0), since no major tags exist after v8; `cache-local-path: ~/.cache/uv`, since turbo strict mode strips UV_CACHE_DIR. The ci.yml comment cites "runbook → Secret exposure", which no prompt writes yet.
- 2026-10-17: CBS-2 committed (5c71218); Commands chain green, gitleaks clean (one `// gitleaks:allow` on the fake sk_live_ test value in @cb/env, copied from fun-run). `.vscode/` added to .gitignore (user approved). Push blocked: the gh token lacks the `workflow` scope.
- 2026-10-17: ledger committed on the CBS-2 branch and shipped in the PR (user choice, overriding the bookkeeping-on-base convention).
