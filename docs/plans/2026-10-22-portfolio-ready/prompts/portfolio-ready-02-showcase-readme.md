---
type: prompt
plan: "[[2026-10-22-portfolio-ready]]"
id: 02
unit: U2
status: todo
model: sonnet
effort: medium
depends_on: [01]
parallel_group: B
files:
  create:
    - docs/images/storefront-home.png
    - docs/images/book-slots.png
    - docs/images/dashboard-overview.png
    - docs/images/dashboard-schedule.png
  modify:
    - README.md
  delete: []
---
# 02 · Showcase README

## Task
Rewrite `README.md` so a recruiter or a court owner, landing on the GitHub repo, sees within one screen what this is,
how to try it live, and why the engineering is worth a look.

1. Copy the user's four screenshots into the repo, byte for byte:
   `mkdir -p docs/images && cp ~/Pictures/kalaro-courts/{storefront-home,book-slots,dashboard-overview,dashboard-schedule}.png docs/images/`.
   If any source file is missing, **stop and report**. Never generate, edit, resize or re-encode them.
2. Rewrite `README.md` as described below, embedding those four images.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`; GitHub `alessandrocruz5/court-booking-system`
  (public, MIT). Read the current `README.md` first. **Keep** its intro paragraph, the venue paragraph, the
  `## Architecture` diagram and bullets, `## Stack`, `## Quickstart`, the `**What's fake.**` paragraph, `## More` and
  `## License`, editing them only where this prompt says.
- Live URLs (public Cloud Run URLs; also `gh variable get WEB_URL` / `BACKEND_URL`):
  - Storefront: `https://cb-web-6699055361.asia-southeast1.run.app`
  - Staff dashboard: `https://cb-backend-6699055361.asia-southeast1.run.app/dashboard/`. The **Explore the owner
    demo** button signs in as a read-mostly VIEWER with masked contact details; no account is needed.
- Screenshots (copied in step 1): `storefront-home.png` (landing), `book-slots.png` (slot picker with a peak price), `dashboard-overview.png` (KPIs,
  revenue, heatmap), `dashboard-schedule.png` (schedule grid). Embed them with relative paths
  `docs/images/<file>.png` and meaningful alt text.
- Final section order:
  1. `# Kalaro Courts: court booking system`, then one badge line:
     `[![CI](https://github.com/alessandrocruz5/court-booking-system/actions/workflows/ci.yml/badge.svg)](https://github.com/alessandrocruz5/court-booking-system/actions/workflows/ci.yml)`,
     the same for `deploy.yml` labelled Deploy, and `[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)`.
  2. The existing intro and venue paragraphs.
  3. `## Live demo`: the storefront link; the dashboard link with the demo-button note; the PayMongo test card
     `4343 4343 4343 4345`; and one sentence saying both services scale to zero on the free tier, so the first page
     can take about 10 seconds to wake up and later pages are fast.
  4. `## Screenshots`: the four images, two of the storefront, then two of the dashboard, each with a one-line
     caption.
  5. `## Demo in 3 minutes`: the existing six steps, with `$WEB_URL` replaced by real links (step 1 links the
     storefront; step 3 links `/staff` on the storefront). Keep `**What's fake.**`.
  6. `## Engineering highlights`: 7–9 bullets, each a bold claim, then one sentence, then a link to the file that
     proves it. Use **only** these facts (all verified):
     - Double booking is impossible at the database level: every slot claim goes through
       `apps/backend/bookings/holds.py` and relies on a `UniqueConstraint` on `SlotLock`
       (`apps/backend/bookings/models.py`), never check-then-insert; unpaid holds last 20 minutes.
     - Payment status comes only from the server: the signed PayMongo webhook (`apps/backend/payments/webhook.py`) and
       a server-side checkout-session lookup both go through one idempotent `confirm_payment()`
       (`apps/backend/payments/confirm.py`), which checks the paid amount against the price snapshotted on the
       booking. URL parameters are never trusted. Late payments are handled: the slot is re-acquired or the booking is
       flagged `needs_refund`.
     - Test mode is enforced in code: only `sk_test_` keys are accepted, and the webhook rejects `livemode: true`.
     - Least-privilege database: the app connects as a role with DML only
       (`apps/backend/core/migrations/0002_app_role.py`); migrations run separately as the owner.
     - Privacy by design (Philippine Data Privacy Act, RA 10173): visitor bookings are anonymized 7 days after they
       end by the nightly job (`apps/backend/bookings/management/commands/nightly.py`); the dashboard masks contact
       details in the query layer (`apps/backend/dashboard/queries.py`), not just in templates; logs and API errors
       carry no personal data, and PayMongo metadata carries only the booking ID.
     - The storefront holds no database credential: Next.js calls the backend's `/api/v1/*` from server code only,
       with a bearer token checked in constant time (`apps/backend/storefront/auth.py`). The two apps share JSON
       contract fixtures that both test suites read (`docs/api/fixtures/`).
     - Hardened web: a per-request CSP nonce (`apps/web/src/lib/csp.ts`), `Cache-Control: no-store` on every API
       response, and rate-limited sign-in and booking lookup stored in Postgres.
     - Twelve-factor builds and keyless deploys: the builds read no environment variables, the images run as
       non-root, and GitHub Actions deploys to Cloud Run through Workload Identity Federation with no stored keys
       (`.github/workflows/deploy.yml`); CI runs a gitleaks secret scan on every pull request and every push to `main`.
     - Runs for $0: Cloud Run (min 0, max 1 instance) and Neon Postgres free tiers.
     Add one bullet with the test counts: run `pnpm test` (it needs `docker compose up -d --wait db`) and use the
     numbers it prints, rounded down to the nearest 10 with a `+` (for example "770+ backend tests, 170+ web
     tests"), linking `.github/workflows/ci.yml`. Add one bullet on process: every change was planned, adversarially
     audited and reviewed before merging, and the plans are in [`docs/plans/`](docs/plans/).
  7. `## Architecture`, `## Stack` and `## Quickstart`, unchanged.
  8. `## Known limits and next steps`: test mode only, and refunds are flagged for manual handling, not automated;
     no customer accounts and no email or SMS confirmations (customers keep their `KC-` reference and look it up);
     one venue in one timezone; cold starts are accepted to stay on the free tier. Next steps: browser end-to-end
     tests, a `starts_at` index on `SlotLock` once data outgrows demo scale, and digest-pinned base images.
  9. `## More` and `## License`, unchanged. No Author section (user decision).
- House style (match the existing README): plain, direct sentences; sentence-case headings; no emoji; no marketing
  superlatives ("blazing", "robust", "seamless"); backticks for paths and code; relative links for repo files. Keep
  the whole README under about 220 lines.
- Review constraints that apply: **Test mode only** (never imply real payments); **Personal data** (no real names,
  emails or mobiles in text or images); **Free tier** (never suggest keep-warm pings). `pnpm format:check` covers only
  TS/JS/JSON (`package.json:15`), so check the README with `pnpm exec prettier --check README.md` (fix it with
  `pnpm exec prettier --write README.md`).

## Do not
- Touch files outside the `files` list, including `docs/runbook.md`, `CLAUDE.md` and `docs/api/`. If you must, stop
  and report why.
- Generate, edit, resize or re-encode the PNGs (only the `cp` in step 1).
- Claim anything not listed above (no uptime figures, no "production-ready", no Lighthouse scores, no email
  features).
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
for f in storefront-home book-slots dashboard-overview dashboard-schedule; do cmp ~/Pictures/kalaro-courts/$f.png docs/images/$f.png; done
pnpm format:check
pnpm exec prettier --check README.md
# every relative link and image resolves (fails on any MISSING), and 4 distinct screenshots are embedded
! ( grep -oE '\]\(([^)#]+)' README.md | sed 's/](//' | grep -v '^http' | while read -r p; do test -e "$p" || echo "MISSING $p"; done ) | grep MISSING
test "$(grep -oE 'docs/images/[a-z-]+\.png' README.md | sort -u | wc -l)" -eq 4
! grep -n '\$WEB_URL\|\$BACKEND_URL' README.md        # no placeholders left
for u in https://cb-web-6699055361.asia-southeast1.run.app/ https://cb-backend-6699055361.asia-southeast1.run.app/dashboard/login/; do curl -s -o /dev/null -w "%{http_code} $u\n" "$u"; done   # 200 each
```
- Report the final section list and the test counts you used.
- Ask the user to confirm, before the PR, that no screenshot shows an unmasked real name, email or mobile.
