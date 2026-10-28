---
type: plan
kind: feature
status: draft
repo: court-booking-system
delivery: pr
base: develop
sprint: 3
epic:
created: 2026-10-28
risk: high
prompts: 12
graph_built: none
tags: [plan, design]
---
# UI redesign: storefront polish, staff Front desk and check-in

## Request
> connect what you made into the repo

"What you made" means the Claude Design prototypes `Kalaro Booking` and `Kalaro Staff`, in `design-spec.md` and `prototypes/`. The goal is a more polished look in both apps without losing simplicity, plus a front-desk check-in flow for staff.

| # | Requirement | Source |
|---|---|---|
| R1 | The web shell, landing, `/book`, result pages and `/booking` match the spec's tokens, type and layout. | Spec: Storefront |
| R2 | The landing shows **Free tonight**: the next free start per sport today, linking into `/book`. | Spec: Landing |
| R3 | `/book` is four step cards plus a sticky summary (a bottom bar under 900px), still URL-param driven. | Spec: Book |
| R4 | The success page shows the reference in a dark card with a Copy button, and **never** claims an email was sent. | Spec; FAQ, `/privacy` |
| R5 | A booking can be **checked in** once, on its day, before it ends, if confirmed and not a block. The check-in time and the staff user are stored. | Spec: Front desk |
| R6 | The viewer may check in only demo or non-online bookings, as with cancel. The owner may check in any eligible booking. | `roles.can_cancel` precedent |
| R7 | The dashboard has a **Front desk** page: lookup by reference (and by name for the owner), one-click check-in, warnings (wrong day, unpaid, late, ended), today's stats, arriving next, on court now. | Spec: Front desk |
| R8 | The dashboard uses the sidebar shell. The schedule renders booking blocks (a full basketball booking spans both halves), with a now marker. Bookings and overview are restyled, and the bookings list filters by derived Checked in and Completed. | Spec: Staff |
| R9 | Every page of both apps still shows "Fictional venue · Test mode, no real payments". Dashboard responses stay CSP-safe (no inline styles or scripts). The viewer still sees masked personal data. | `CLAUDE.md` constraints |
| R10 | `/privacy` and the runbook reflect the new stored field and the migration step. | RA 10173; DB roles |

## Context used
- The spec and prototypes: `design-spec.md` (the handoff README) and `prototypes/*.dc.html`, with the clock fixed at Sun 25 Oct 2026 19:48.
- `CLAUDE.md`: Review constraints, High-stakes paths, Hidden coupling. `docs/plans/2026-10-21-follow-up-fixes/*` for the format and the `now`-threading convention.
- Code read:
  - `apps/web/app/{layout,page,globals.css}`, `app/book/page.tsx`
  - `src/content/site.ts`
  - `bookings/{models,rules,pricing}.py`
  - `accounts/roles.py`
  - `dashboard/{views,urls}.py`, `dashboard/templates/dashboard/base.html`
  - the function list of `dashboard/{queries,schedule}.py`
  - `storefront/urls.py`
- Facts the plan relies on:
  - `Status` has no check-in state. `Source.WALK_IN = "walk_in"`.
  - `queries.overview` already computes revenue, by-sport, heatmap and upcoming.
  - Templates use Django 6 partials (`schedule.html#grid`).
  - `getAvailabilityOnce` exists in `src/lib/api/client.ts`.

## Options
**Where check-in state lives (R5)**

| Option | Cost | Risk | Notes |
|---|---|---|---|
| A. Nullable `checked_in_at` and `checked_in_by` on `Booking` (expand-only migration 0003) | 1 opus prompt | Medium: a laptop migration before deploy | Status stays `confirmed`, so payments, cancel and the nightly job are untouched |
| B. A new `Status.CHECKED_IN` | Similar | High: every `status ==` check, `_CANCELLABLE`, the API payloads and fixtures change | Bigger blast radius |

**Recommendation:** A.

**Free tonight data (R2)**

| Option | Cost | Risk | Notes |
|---|---|---|---|
| A. 5 parallel `availability` calls on the landing, in their own Suspense | Web only | Low; 5 extra API hits per landing view (free tier) | No contract change |
| B. A new `next_free` field on `catalog` | Contract change (views/payloads ↔ fixtures ↔ `schemas.ts`) | Medium | Cheaper at runtime |

**Recommendation:** A. Revisit if Neon CU-hours climb.

## Decisions
- **Repo rules win over the prototype** (spec, "Where the prototype differs"):
  - no "copy sent to email"
  - FAQ copy from `site.ts`
  - real `KC-` references, `Court.name` and `payment_method`
  - viewer masking and preset block reasons
- **Check-in is a column, not a status** (Option A). "Checked in" and "Completed" are derived in `dashboard/queries.py` for display and filters only.
- **Viewer check-in** mirrors `can_cancel`: demo or non-online only. **Name search on the desk is owner-only**, because a viewer's name search would match unmasked names.
- **The dashboard landing stays Overview at `""`.** Front desk is at `desk/` and is first in the nav. *Open question for the user: make the desk the landing?* That would change `""` and the post-sign-in redirect.
- **CSP**: no inline styles in the dashboard. Grid placement, bar widths, heat buckets and the now offset use generated utility classes in `dashboard.css`.
- **Fonts**: self-hosted woff2 for Django (`core/static/core/fonts`, OFL); `next/font/google` for web, as Archivo is today.
- **Base `develop`**: units are PRs into `develop`, and **Release** is a `develop → main` PR.

**Non-goals:** customer self check-in, QR codes, email/SMS, a new booking status, API contract changes, a dark mode, mobile layouts for the dashboard beyond the sidebar collapsing to a top bar.

## Change list
| File | Action | Why | Req | Prompt |
|---|---|---|---|---|
| `apps/web/app/globals.css`, `app/layout.tsx`, `src/components/test-mode-banner.tsx` | M | Tokens, fonts, shell | R1 R9 | 01 |
| `apps/web/src/content/sports.ts` (+ test) | C | Sport colours, tested against `catalog.json` | R1 | 01 |
| `apps/web/app/page.tsx`, `src/components/landing/free-tonight.tsx` (+ test) | M/C | Landing | R1 R2 | 02 |
| `apps/web/app/book/{page,loading}.tsx`, `src/components/booking/*` | M/C | Step cards, summary, bottom bar, overlay | R3 | 03 |
| `apps/web/app/book/{success,cancelled}/page.tsx`, `app/booking/page.tsx`, `lookup-form.tsx`, `copy-reference.tsx` (+ tests) | M/C | Result and lookup pages | R1 R4 | 04 |
| `apps/backend/bookings/models.py`, `migrations/0003_booking_check_in.py`, `bookings/checkin.py` (+ test) | M/C | Check-in columns and service | R5 | 05 |
| `apps/backend/accounts/roles.py` (+ test), `dashboard/desk.py` (+ test), `dashboard/queries.py` | M/C | Permission, desk read models, derived statuses | R6 R7 R8 R9 | 06 |
| `core/static/core/{base.css,fonts/*}`, `dashboard/static/dashboard/dashboard.css`, `dashboard/templates/dashboard/base.html`, `templates/base.html` | M/C | Sidebar shell, tokens, fonts | R8 R9 | 07 |
| `dashboard/{views,urls}.py`, `templates/dashboard/desk.html`, `tests/test_desk.py` | M/C | Front desk and check-in action | R7 | 08 |
| `dashboard/schedule.py`, `templates/dashboard/schedule.html`, `tests/test_schedule.py` | M | Block grid, now marker, panel check-in | R8 | 09 |
| `templates/dashboard/{bookings,booking_detail}.html`, `tests/test_bookings.py` | M | List and detail restyle | R8 | 10 |
| `templates/dashboard/overview.html`, `dashboard/queries.py`, `tests/test_overview.py` | M | Overview restyle | R8 | 11 |
| `bookings/demo.py` (+ test), `apps/web/app/privacy/page.tsx`, `docs/runbook.md` | M | Demo check-ins, privacy, migration runbook | R10 | 12 |

## Blast radius
**Risk:** high. It touches `bookings/models.py`, a migration, `accounts/**`, `bookings/demo.py` and `app/book/success/**`.

| Affected | Kind | Via | Breaks? | Mitigation |
|---|---|---|---|---|
| Every web page | Direct | New shell and tokens | No: the class names are kept until replaced | Existing banner tests |
| `/book` tests | Direct | Markup changes (StepHeader removed) | Possibly | 03 updates only the removed-markup assertions |
| `/book/success` | High-stakes | Markup only | No: the data path is untouched | 04 `git diff` review; code-guardian |
| `Booking` rows | Schema | Two nullable columns | No | Expand-only. Applied before deploy (runbook, 12) |
| `holds.cancel_booking` | Non-graph | The check constraint, if added | **Yes** if a checked-in booking can be cancelled | 05 checks first and drops the constraint if so |
| API payloads and fixtures | Contract | — | No: no payload changes | — |
| Nightly anonymization | Non-graph | New column | No: it isn't personal data | 12 updates `/privacy` |
| Dashboard header tests | Direct | Sidebar shell | Yes (selectors) | 07 updates them and lists each |
| Schedule tests | Direct | Grid shape | Yes (markup) | 09 keeps `Row` data or updates the tests and lists them |
| CSP | Constraint | New templates | Only with inline styles | `assert_csp_safe` on every new response |
| Viewer masking | Constraint | Desk search | Yes, if name search were allowed | Owner-only name search (06) |
| `seed_demo` | High-stakes | Check-ins | No | 12 uses `checkin` rules; demo markers kept |

## Units
| Unit | Title | Category | Prompts | Depends | High-stakes | Acceptance criteria |
|---|---|---|---|---|---|---|
| CBS-17 | Storefront redesign | Changed | 01–04 | — | yes (04) | R1–R4: pages match the spec; Free tonight links into `/book`; no "sent to" on success; web suite green |
| CBS-18 | Check-in model and permission | Added | 05, 06 | — | yes | R5 R6: check-in rules and idempotency tested; viewer matrix tested |
| CBS-19 | Dashboard redesign and Front desk | Added/Changed | 07–11 | CBS-18 | no (templates and views) | R7 R8 R9: desk works with and without htmx; full-court blocks span both halves; CSP-safe; masked for the viewer |
| CBS-20 | Demo data, privacy, runbook | Changed | 12 | CBS-19 | yes (`demo.py`) | R10 |

Merge order: CBS-17 and CBS-18 can go in parallel, then CBS-19, then CBS-20. Each is a PR into `develop`.

**Release:** before the `develop → main` PR, the user applies migration 0003 with `MIGRATE_DATABASE_URL` (runbook, 12).

## Prompts
| # | Title | Unit | Model | Effort | Depends | Group |
|---|---|---|---|---|---|---|
| 01 | Web tokens, sport colours and the shell | CBS-17 | sonnet | medium | — | A |
| 02 | Landing: Free tonight, rates table, FAQ | CBS-17 | sonnet | medium | 01 | A |
| 03 | /book: step cards and sticky summary | CBS-17 | sonnet | high | 02 | A |
| 04 | Success, cancelled and Find booking pages | CBS-17 | opus | medium | 03 | A |
| 05 | Check-in columns, migration and service | CBS-18 | opus | high | — | B |
| 06 | can_check_in, desk queries, derived statuses | CBS-18 | opus | high | 05 | B |
| 07 | Dashboard shell: sidebar, tokens, fonts | CBS-19 | sonnet | medium | 06 | C |
| 08 | Front desk page and check-in action | CBS-19 | opus | high | 07 | C |
| 09 | Schedule block grid, now marker, panel check-in | CBS-19 | sonnet | high | 08 | C |
| 10 | Bookings list and detail restyle | CBS-19 | sonnet | medium | 09 | C |
| 11 | Overview restyle | CBS-19 | sonnet | medium | 10 | C |
| 12 | Demo check-ins, privacy, runbook | CBS-20 | opus | medium | 11 | D |

Why opus:
- 04: `app/book/success/**`
- 05: models and migrations
- 06: `accounts/**`
- 08: a new write path with a permission and the viewer budget
- 12: `bookings/demo.py`

## End-to-end verification
```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend
! grep -rn 'sent to' apps/web/app/book/success/page.tsx
cd apps/backend && uv run python manage.py makemigrations --check --dry-run && cd ../..
```
Manual checks, in test mode after the Release:
- Book a court and copy the reference.
- Sign in as the owner, then on Front desk paste the reference and check in. The toast shows, the schedule block turns green, and the bookings list's "Checked in" filter shows it.
- Sign in as the viewer: contact details are masked, name search returns nothing, and checking in a real online booking returns a 403.

## Rollback
- Revert the unit's merge on `develop`, and on `main` if it's already released.
- Migration 0003 only adds nullable columns, so the old code ignores them. Leave the migration applied; a later contract plan can drop the columns.

## Log
- 2026-10-28: planned from the Claude Design handoff (prototypes `Kalaro Booking`, `Kalaro Staff`). Status draft; next step `/audit-plan`.
