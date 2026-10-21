# Kalaro Courts — Sprints
Status: [ ] planned · [~] in progress · [x] merged · [-] cancelled (excluded from changelog)

> Each unit's plan, prompts and acceptance criteria are in its `plan:` link. `/build-unit {KEY-id}` runs them.

## Sprint 1 — Court booking MVP   (planned 2026-10-16)
Epic: CBS-1 · Branch base: `main` · Plan: [[2026-10-16-court-booking-mvp]]

> **Epic:** A portfolio court-booking system for the fictional Kalaro Courts: a Next.js customer storefront and a
> Django + HTMX staff dashboard on Neon Postgres and Cloud Run (free tier), with PayMongo in test mode only.

- [x] CBS-2 — Monorepo scaffold, CI and project profile · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 01, 02, 03, 04 · depends: — · model: opus (merged 2026-10-17)
  - **Story:** Sets up the pnpm + Turborepo monorepo with the Django and Next.js skeletons, CI (Postgres and gitleaks), and the project's `CLAUDE.md`, README and runbook.
  - **Result:** PR #1. Django 6.1.2 / Python 3.14 backend (21 tests), Next 16 storefront shell (13 tests), `@cb/env` (4 tests); CI `verify` + `secrets` green; `CLAUDE.md` now holds `## Commands`, the review constraints and the high-stakes paths.
  - **Downstream:**
    - CI pins actions by SHA where no major tag exists: `astral-sh/setup-uv` has had none since v8 (05 should check each new action's tags).
    - Turbo strict env mode strips every variable not in `globalPassThroughEnv` (now only `TEST_DATABASE_URL`). CI sets setup-uv's `cache-local-path: ~/.cache/uv` for that reason. A prompt that needs a new env var inside a turbo task must add it there.
    - `ci.yml`'s gitleaks comment cites "runbook → Secret exposure", which doesn't exist yet. Assign it to 06, which wires the secrets.
    - The README and `CLAUDE.md` link to `docs/api/`, which 12 creates.
    - Gitleaks flags fake `sk_live_`/`sk_test_` values in tests (the `@cb/env` test carries `// gitleaks:allow`). The PayMongo prompts (10, 11, 13) must do the same, or use values that don't match the Stripe rule.
    - `.vscode/` is gitignored. Locally, `pnpm` needs `sudo corepack enable` (or `corepack enable --install-directory <dir on PATH>`) for turbo to find it.
- [x] CBS-3 — Container images and Cloud Run deploy · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 05, 06 · depends: CBS-2 · model: opus (merged 2026-10-20)
  - **Story:** Builds non-root Docker images for both apps and a GitHub Actions pipeline that deploys them to Cloud Run (min 0 / max 1 instances) without stored keys.
  - **Result:** PR #2. Web image 269 MB (uid 1000), backend 176 MB (uid 999), both built with no env; CI `images` job smoke-runs both and checks fail-fast env validation. `deploy.yml` (WIF, `gcloud` deploys of `cb-backend`, `cb-web`, job `cb-nightly`) is skipped until `vars.GCP_PROJECT_ID` is set. Runbook: `## Cloud Run (once)`, `## Deploy`, `## Roll back`, `## Secret exposure`. Gate: CI + code-guardian (1 Blocker, 4 Should-fixes fixed).
  - **Downstream:**
    - A new runtime env key goes in four places: `config/env.py`, the CI `images` smoke `env_args`, `deploy.yml` `--set-env-vars`/`--set-secrets`, and the runbook. A new secret also breaks the 6-active-version Secret Manager free allowance, so prefer reusing one.
    - `.dockerignore` must keep excluding `**/gha-creds-*.json` (the auth action's credential file; the web build context is the repo root).
    - The backend image has no `ENTRYPOINT`; `cb-nightly` runs `python manage.py nightly`, which a later unit adds. Nothing schedules the job until then.
    - The WIF condition accepts only `deploy.yml@refs/heads/main` on `workflow_run`/`workflow_dispatch`. Renaming `deploy.yml` breaks sign-in until the provider is updated.
    - `apps/backend/.dockerignore` excludes `**/tests`, so tests are never in the image.
    - Follow-ups (not scheduled): `control_socket_disable = True` in `config/gunicorn.conf.py` (gunicorn 26 control socket; the image gives `app` a home dir meanwhile); code-guardian nits in the plan Log (digest-pinned base images, Dependabot major/minor ignore, `BACKEND_HOST` trailing slash, `run.developer` instead of `run.admin`).
    - Local tooling: Docker needs the `docker-buildx` package; `docker compose` needs the compose plugin (`docker-compose` package) for the `## Commands` chain.
- [x] CBS-4 — Booking engine: courts, rules, holds · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 07, 08, 09 · depends: CBS-3 · model: opus (merged 2026-10-20)
  - **Story:** Adds the courts, bookings, rules, pricing and 20-minute payment holds, plus the least-privilege DB role. The database itself makes double-booking impossible.
  - **Result:** PR #6 (merge 83269dc). `bookings` app (Court/Booking/SlotLock, 18 courts in `0002_courts`), `rules`, `pricing`, `references`, `availability`, `holds`; `core` RateLimit (`hit`/`prune`) and `0002_app_role` (`cb_app` DML only); runbook `## Database roles and migrations`. 135 backend tests, concurrency tests stable. Gate: CI + code-guardian (0 Blockers; all Should-fixes fixed; re-review APPROVE WITH NITS).
  - **Downstream:**
    - New tables: `bookings_court`, `bookings_booking`, `bookings_slotlock`, `core_ratelimit`. Booking already carries `checkout_session_id`, `price_centavos`, `payment_id`, `payment_method`, `fee_centavos`, `net_centavos`, `paid_at`, `hold_expires_at`, so CBS-5 needs no booking migration for them.
    - `holds.reacquire` must run inside `atomic()`, accepts an `expired` or lapsed `pending` online booking (`ValueError` otherwise), and returns False once `starts_at <= now`. `release` takes only cancelled/expired/needs_refund, and `expired` only from `pending`. The full contract is in prompt 11's Context.
    - Built beyond the spec: `rules.validate_search` and `STAFF_WINDOW_DAYS = 30` (for CBS-6/CBS-10); `create_staff_booking` raises for a block without a note or a walk-in without a sport.
    - Deferred: occupancy/prune indexes (fine at demo scale).
- [x] CBS-5 — PayMongo payments · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 10, 11 · depends: CBS-4 · model: opus (merged 2026-10-20)
  - **Story:** Connects PayMongo in test mode: checkout sessions, the signed webhook, and one idempotent payment confirmation that also handles late payments.
  - **Result:** PR #7 (merge 12e59a3). `payments` app: `paymongo` (Hosted Checkout client, `get_client()`), `env`, `webhook` (signature/event parsing), `confirm` (`confirm_payment`, `check_checkout`, `release_checkout`), `POST /webhooks/paymongo`; runbook `## PayMongo (test mode)`; httpx 0.28.1. 332 backend tests. Gate: CI + code-guardian (1 Blocker + 5 Should-fixes fixed; re-review 0 Blockers, 1 Should-fix fixed), then CI only on 2f3fc46.
  - **Downstream:**
    - New env keys `PAYMONGO_SECRET_KEY` (only `sk_test_`) and `PAYMONGO_WEBHOOK_SECRET` (≥ 24 chars; the public `pending` placeholder fails closed). No new tables.
    - `PayMongoClient` is a context manager: `with get_client() as client:`. Never call it inside `atomic()`.
    - `check_checkout` raises RuntimeError inside `atomic()`, so its API tests must be transactional (`serialized_rollback=True`). It returns `pending` for an expired/cancelled booking with no payment; CBS-6/7 decide what the page shows. Prompt 13's Context records all of this.
    - `release_checkout` re-checks status under `select_for_update` and never cancels a concurrently confirmed booking; it expires the PayMongo session via `on_commit`.
    - Unknown or live paid sessions log WARNING and are not refunded (the PayMongo account is shared with fun-run and local dev).
    - Deferred nits: `/webhooks/*` no-store on 404/400 raised outside the view; a JSON 405 (today `require_POST` returns a no-store HTML 405).
- [x] CBS-6 — Storefront API · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 12, 13 · depends: CBS-5 · model: opus (merged 2026-10-20)
  - **Story:** Exposes the token-guarded JSON API the storefront calls (catalog, availability, booking, checkout, lookup), pinned by shared contract fixtures.
  - **Result:** PR #8 (merge fc7ad11). `storefront` app under `/api/v1/`: `GET catalog` (0 queries), `GET availability`, `POST bookings` (hold + PayMongo session after commit), `POST checkout/confirm`, `POST checkout/release`, `POST bookings/lookup`; `require_service_token` (503 under 32 chars, constant time, no-store); 7 fixtures in `docs/api/fixtures/`, `docs/api/README.md`; 427 backend tests. Gate: CI + code-guardian (4 SFs + nits fixed; re-review APPROVE WITH NITS), then CI only on 6e7e200.
  - **Downstream:**
    - No new tables or env keys beyond `INTERNAL_API_TOKEN` (≥ 32 chars). Request bodies use `customer.name|email|mobile`; the web client forwards the visitor IP, which the backend's `client_ip` normalises (IPv6 keyed on /64).
    - `checkout/confirm` answers `expired`/`cancelled` for a released or lapsed unpaid hold, not `pending`. Prompt 16 copy must say the payment "may still go through" and offer Check again (code-guardian SF, user choice). Take nullability from `docs/api/README.md`, not from the fixtures (prompt 14 Context).
    - Invalid requests don't count against the rate limits; lookup 404s are identical for wrong reference and wrong email.
    - Deferred: expire the orphaned PayMongo session when the session-id save fails; optional /48 bucket; unmatched `/api/v1/*` 404s lack no-store.
- [x] CBS-7 — Customer booking site · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 14, 15, 16, 17 · depends: CBS-6 · model: opus (merged 2026-10-20)
  - **Story:** Builds the customer site: pick a sport, date, court and time, pay on PayMongo's test checkout, get a reference and look it up later. Adds the landing and privacy pages.
  - **Result:** PR #9 (merge 7ae2230). `server-only` zod API client (`src/lib/api/`, runtime parse-equals-fixture drift test), `/book` browse flow (URL state, no JS needed), `startCheckout` action + httpOnly `cb_checkout` cookie, cookie-only `/book/success` and `/book/cancelled`, landing with live rates (fallback when the backend is down), `/booking` POST lookup, `/privacy`, `/staff` redirect; 120 web tests. Gate: CI + code-guardian (REQUEST CHANGES, 0 Blockers → fixed in 55d5490; re-review APPROVE WITH NITS → fixed in 1037802), then CI only on 1037802.
  - **Downstream:**
    - No new tables, endpoints or env keys. Web tests read `docs/api/fixtures` with `readFileSync`, never a static JSON import (the web image's build context excludes `docs/`, and `next build` typechecks tests).
    - `/privacy` now promises: visitor bookings anonymized `RETENTION_DAYS` (7, in `apps/web/src/content/site.ts`) after they end, so within 8 days; rate-limit entries deleted within a day; PayMongo receives booking ID, sport, date and name/email/mobile; hosting in Singapore. CBS-8 (prompt 18) must ship soon and match it; until it does, the page overstates the retention.
    - `CHECKOUT_COOKIE` is defined in both `app/book/{success,cancelled}` pages (Next 16 forbids non-async exports from a `"use server"` file). Change both with `actions.ts`.
    - Follow-ups (not scheduled): verify `clientIpFrom` on deployed Cloud Run (covered by prompt 24 checklist step 9's two-network `/booking` test); `docs/api/README.md` should list `BookingSummary.sport` as nullable; release the hold on the unreachable bad-checkout-URL branch; two tabs share one `cb_checkout` cookie; `releaseHold`'s redundant second (idempotent) release.
- [x] CBS-8 — Demo data and nightly job · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 18 · depends: CBS-7 · model: opus (merged 2026-10-21)
  - **Story:** Fills the demo with realistic bookings, and adds the nightly job that expires holds, anonymizes visitor data after 7 days and reseeds the demo.
  - **Result:** PR #10 (merge bbf6c13). `bookings/demo.py` (in-memory seeded plan, each booking claimed through `claim_slots` in its own `atomic()`, ~3,300 bookings / ~20 s locally), `manage.py seed_demo` (exit 2 without `ALLOW_DEMO_SEED=1`), `manage.py nightly` (expire holds → anonymize non-demo bookings 7 days after they end → prune rate limits > 10 min → clear sessions → reseed; counts-only logs under `cb.nightly`, exit 1 if any step fails); runbook `## Demo data and nightly job`; `ALLOW_DEMO_SEED` in `.env.example`; 444 backend tests. Gate: CI + code-guardian (REQUEST CHANGES, 0 Blockers, 3 SFs → fixed in be5a35b; CI flake fixed in 267e158; re-review APPROVE WITH NITS, merged as is).
  - **Downstream:**
    - No new tables, endpoints or migrations. New env key `ALLOW_DEMO_SEED` (not required; `deploy.yml` already sets it on `cb-nightly` only).
    - The demo seed skips slots of real unpaid online bookings (pending/expired, not started) so a late payment can still `reacquire`. Real rows are never deleted; their personal data is cleared by `nightly.anonymize` (name, email, mobile; `note` is not cleared).
    - `nightly.RATE_LIMIT_MAX_AGE` (10 min) must be ≥ every rate-limit window (today `storefront.views.WINDOW_SECONDS = 600`). CBS-9's sign-in limiter must not use a longer window, or must raise it (no test ties them yet).
    - `nightly.RETENTION_DAYS = 7` duplicates `RETENTION_DAYS` in `apps/web/src/content/site.ts` (`/privacy`), with no drift test.
    - One-time ops after the deploy: create the `cb-scheduler` service account and the `cb-nightly-trigger` Scheduler job (runbook); check the first execution's duration on Neon (estimate 1–2 min, timeout 600 s).
    - Follow-ups (not scheduled): drift tests for the two constants above; a 10-minute prune-boundary test; "never changed" wording (claim_slots' stale-lock cleanup can still expire an already-started real hold); advisory lock against concurrent runs; halves at ~36% vs ~30%; `clear_sessions` counts with `timezone.now()`; `seed_demo` prints only the created count; `_is_reference_clash` duplicated from holds.py.
- [x] CBS-9 — Staff sign-in and dashboard overview · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 19, 20, 21 · depends: CBS-8 · model: opus (merged 2026-10-21)
  - **Story:** Adds staff sign-in (a seeded owner and a public demo viewer, rate-limited) and the dashboard overview: KPIs, revenue by sport and a utilization heatmap.
  - **Result:** PR #11 (merge 6d75cc6). `accounts` app: `Role`/`role_of`/`can_see_personal_data`/`can_create_staff_booking`/`can_cancel`, `@staff_required` (never_cache, HTMX `HX-Redirect`), redirect-only `DashboardLoginRedirectMiddleware`, `seed_staff`; `/dashboard/login/`, `/dashboard/demo/` (posts only CSRF), `POST /dashboard/logout/`, 5 sign-ins/60 s per IP in Postgres (fails closed); `core/http.client_ip` (rightmost XFF, IPv6 /64); `templates/base.html` + 400/403/403_csrf/404/500 with the banner; `dashboard` app: `queries.overview` (masking here), overview page, vendored htmx 2.0.11; `/` → `/dashboard/`; runbook `## Staff dashboard`; 588 backend tests. Gate: CI + code-guardian (APPROVE WITH NITS, 4 SFs → fixed in b15aa1a; re-review APPROVE WITH NITS → nits fixed in ddd2094), then CI only.
  - **Downstream:**
    - No new tables, migrations or env keys (`STAFF_OWNER_*`/`DEMO_VIEWER_*` are laptop/`seed_staff` inputs; `DEMO_VIEWER_*` was already wired in deploy.yml).
    - Dashboard views: wrap each in `@staff_required` (outermost) and read `request.staff_role`; data comes only from `dashboard/queries.py`, masked there (`mask_name`/`mask_email`/`mask_mobile`, `name_for(role, name)`). Use `accounts.roles.can_cancel` / `can_create_staff_booking` on the server.
    - Templates extend `dashboard/base.html` and fill `dashboard_title` / `dashboard_content`. `templates/base.html` owns `<body>`, so the CSRF `hx-headers` sits on the dashboard header and the content wrapper: every htmx element must live inside those. htmx config forbids eval and script tags: no inline scripts, no `hx-on`. Add nav links in `dashboard/base.html`.
    - `seed_staff` deletes **every** `django_session` row (only staff use Django sessions) and deactivates role members left by a changed email. Keep it true: don't add other session users. Messages storage is cookie-first; a large message set would spill into the session.
    - Sign-in window 60 s ≤ `nightly.RATE_LIMIT_MAX_AGE` (tested).
    - CBS-10 prompt 24's release checklist should run the runbook's `## Staff dashboard` "Check it" steps on Cloud Run (second-network lockout check and the spoofed-XFF curl loop), and check the browser console for CSP violations (not checked yet).
    - Follow-ups (not scheduled): SlotLock `starts_at` index (heatmap/today queries; expand-only migration); `storefront.views._client_ip` duplicates `core/http._normalise`.
- [ ] CBS-10 — Dashboard operations and release checklist · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 22, 23, 24 · depends: CBS-9 · model: opus
  - **Story:** Adds the schedule grid (walk-ins, blocks, cancellations), the searchable bookings list, and the pre-release checklist and demo script.
