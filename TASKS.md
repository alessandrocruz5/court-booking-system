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
- [ ] CBS-6 — Storefront API · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 12, 13 · depends: CBS-5 · model: opus
  - **Story:** Exposes the token-guarded JSON API the storefront calls (catalog, availability, booking, checkout, lookup), pinned by shared contract fixtures.
- [ ] CBS-7 — Customer booking site · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 14, 15, 16, 17 · depends: CBS-6 · model: opus
  - **Story:** Builds the customer site: pick a sport, date, court and time, pay on PayMongo's test checkout, get a reference and look it up later. Adds the landing and privacy pages.
- [ ] CBS-8 — Demo data and nightly job · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 18 · depends: CBS-7 · model: opus
  - **Story:** Fills the demo with realistic bookings, and adds the nightly job that expires holds, anonymizes visitor data after 7 days and reseeds the demo.
- [ ] CBS-9 — Staff sign-in and dashboard overview · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 19, 20, 21 · depends: CBS-8 · model: opus
  - **Story:** Adds staff sign-in (a seeded owner and a public demo viewer, rate-limited) and the dashboard overview: KPIs, revenue by sport and a utilization heatmap.
- [ ] CBS-10 — Dashboard operations and release checklist · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 22, 23, 24 · depends: CBS-9 · model: opus
  - **Story:** Adds the schedule grid (walk-ins, blocks, cancellations), the searchable bookings list, and the pre-release checklist and demo script.
