# Changelog — Kalaro Courts

Versions roll up per sprint (MINOR) and per hotfix (PATCH); units and results are in [TASKS.md](TASKS.md).

## [0.3.0] — 2026-10-28 (Sprint 3: UI redesign)

### Added

- Booking check-in: nullable `checked_in_at`/`checked_in_by` (expand-only migration `bookings.0003`), one check-in per booking on its day, and a viewer rule matching cancel (CBS-19).
- Sidebar staff dashboard with a Front desk (lookup, suggestions, arriving, on court, check in), a block schedule grid, and restyled bookings and overview pages (CBS-20).

### Changed

- Storefront redesign: new tokens and shell, Free tonight on the landing, step-card `/book` with a sticky summary, and a dark reference card on success (CBS-18).
- `/privacy` lists the check-in time and staff account; the runbook covers the 0003 rollout (CBS-21).

## [0.2.0] — 2026-10-21 (Sprint 2: Follow-up fixes)

### Changed

- Drift tests tie the rate-limit windows to the prune age and the backend's retention days to the web's; runbook check before a manual nightly run (CBS-15).

### Fixed

- `Cache-Control: no-store` on every `/api/` and `/webhooks/` response; gunicorn control socket off; one IP normaliser (CBS-12).
- One checkout-session expiry, also for sessions created but never saved (CBS-13).
- Dashboard hardening for the demo viewer: cancel only before a booking ends, NUL bytes give 404, budget charged after validation, no bare fragments without htmx, preset block reasons (CBS-14).
- Per-tab checkout: success and cancel URLs carry `?ref=`, and `cb_checkout` holds up to 3 bookings; cause-neutral refund copy (CBS-16).

## [0.1.0] — 2026-10-21 (Sprint 1: Court booking MVP)

### Added

- pnpm + Turborepo monorepo, CI and project profile (CBS-2).
- Container images and Cloud Run deploy (CBS-3).
- Booking engine: courts, rules and slot holds (CBS-4).
- PayMongo payments in test mode (CBS-5).
- Storefront API (CBS-6).
- Customer booking site (CBS-7).
- Demo data and the nightly job (CBS-8).
- Staff sign-in and dashboard overview (CBS-9).
- Dashboard operations (schedule, walk-ins, blocks, cancel, bookings search) and the release checklist (CBS-10).
