# Kalaro Courts — Sprints
Status: [ ] planned · [~] in progress · [x] merged · [-] cancelled (excluded from changelog)

> Each unit's plan, prompts and acceptance criteria are in its `plan:` link. `/build-unit {KEY-id}` runs them.

## Sprint 1 — Court booking MVP   (planned 2026-10-16)
Epic: CBS-1 · Branch base: `main` · Plan: [[2026-10-16-court-booking-mvp]]

> **Epic:** A portfolio court-booking system for the fictional Kalaro Courts: a Next.js customer storefront and a
> Django + HTMX staff dashboard on Neon Postgres and Cloud Run (free tier), with PayMongo in test mode only.

- [~] CBS-2 — Monorepo scaffold, CI and project profile · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 01, 02, 03, 04 · depends: — · model: opus
  - **Story:** Sets up the pnpm + Turborepo monorepo with the Django and Next.js skeletons, CI (Postgres and gitleaks), and the project's `CLAUDE.md`, README and runbook.
- [ ] CBS-3 — Container images and Cloud Run deploy · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 05, 06 · depends: CBS-2 · model: opus
  - **Story:** Builds non-root Docker images for both apps and a GitHub Actions pipeline that deploys them to Cloud Run (min 0 / max 1 instances) without stored keys.
- [ ] CBS-4 — Booking engine: courts, rules, holds · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 07, 08, 09 · depends: CBS-3 · model: opus
  - **Story:** Adds the courts, bookings, rules, pricing and 20-minute payment holds, plus the least-privilege DB role. The database itself makes double-booking impossible.
- [ ] CBS-5 — PayMongo payments · Added · plan: [[2026-10-16-court-booking-mvp]] prompts: 10, 11 · depends: CBS-4 · model: opus
  - **Story:** Connects PayMongo in test mode: checkout sessions, the signed webhook, and one idempotent payment confirmation that also handles late payments.
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
