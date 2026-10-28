---
type: plan
kind: feature
status: in-progress
repo: court-booking-system
delivery: pr
base: develop
sprint: 3
epic: CBS-17
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
| R7 | The dashboard has a **Front desk** page: lookup by reference (and by name: any booking for the owner, demo bookings only for the viewer, as the bookings search), one-click check-in, warnings (wrong day, unpaid, late, ended), today's stats, arriving next, on court now. | Spec: Front desk |
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
- **One derived-status rule** (audit): `queries.status_key(booking, now)`. A confirmed booking that has ended is `completed`; otherwise one with `checked_in_at` set is `checked_in`; otherwise `confirmed`. The schedule imports it and never re-derives it.
- **The derived filters are additive** (audit): `status=checked_in` (confirmed, `checked_in_at` set, not ended) and `status=completed` (confirmed, ended). Plain `status=confirmed` keeps meaning `status=confirmed`.
- **No check constraint on check-in** (audit): `cancel_booking` cancels confirmed bookings, so a checked-in booking stays cancellable under `can_cancel` (a paid online one still ends as `needs_refund`).
- **Viewer check-in** mirrors `can_cancel`: demo or non-online only. **Desk name search reuses `queries._search`** (audit): the owner searches every name, the viewer only demo bookings' names, as the bookings list already does.
- **Desk stats reuse the overview** (audit): `desk.py` imports `_today`, `_alerts`, `_lock_counts`, `SPACE_COUNT`, `UPCOMING_HOURS` and `_clock` from `queries`.
- **No demo check-in seeding** (audit): `cb-nightly` reseeds at 03:00 Manila, before any booking that day has started, so seeded check-ins would never show. Live check-in states come from the viewer checking in demo bookings (R6).
- **The landing now touches the DB** (audit): `catalog` is static, but Free tonight runs 5 `availability` queries per landing render, crawlers included. Accepted for portfolio traffic; revisit if Neon CU-hours climb.
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
| `apps/backend/accounts/roles.py` (+ test), `dashboard/desk.py` (+ test), `dashboard/queries.py`, `dashboard/views.py` | M/C | Permission, desk read models, derived statuses | R6 R7 R8 R9 | 06 |
| `core/static/core/{base.css,fonts/*}`, `dashboard/static/dashboard/dashboard.css`, `dashboard/templates/dashboard/base.html`, `templates/base.html`, `tests/test_{bookings,schedule}.py` | M/C | Sidebar shell, tokens, fonts | R8 R9 | 07 |
| `dashboard/{views,urls}.py`, `templates/dashboard/desk.html`, `tests/test_desk.py` | M/C | Front desk and check-in action | R7 | 08 |
| `dashboard/schedule.py`, `templates/dashboard/schedule.html`, `tests/test_schedule.py` | M | Block grid, now marker, panel check-in | R8 | 09 |
| `templates/dashboard/{bookings,booking_detail}.html`, `tests/test_bookings.py` | M | List and detail restyle | R8 | 10 |
| `templates/dashboard/overview.html`, `dashboard/queries.py`, `tests/test_overview.py` | M | Overview restyle | R8 | 11 |
| `apps/web/app/privacy/page.tsx`, `docs/runbook.md` | M | Privacy notice, migration runbook | R10 | 12 |

## Blast radius
**Risk:** high. It touches `bookings/models.py`, a migration, `accounts/**` and `app/book/success/**`.

| Affected | Kind | Via | Breaks? | Mitigation |
|---|---|---|---|---|
| Every web page | Direct | New shell and tokens | No: the class names are kept until replaced | Existing banner tests |
| `/book` tests | Direct | Markup changes (StepHeader removed) | Possibly | 03 updates only the removed-markup assertions |
| `/book/success` | High-stakes | Markup only | No: the data path is untouched | 04 `git diff` review; code-guardian |
| `Booking` rows | Schema | Two nullable columns | No | Expand-only. Applied before deploy (runbook, 12) |
| `holds.cancel_booking` | Non-graph | The check constraint, if added | **Yes**: `release` cancels confirmed bookings (`holds.py:256`) | No constraint (Decisions); 05 tests cancelling a checked-in booking |
| API payloads and fixtures | Contract | — | No: no payload changes | — |
| Nightly anonymization | Non-graph | New column | No: it isn't personal data | 12 updates `/privacy` |
| Dashboard header tests | Direct | Sidebar shell | Yes (selectors) | 07 updates them and lists each |
| Schedule tests | Direct | Grid shape | Yes (markup) | 09 keeps `Row` data or updates the tests and lists them |
| CSP | Constraint | New templates | Only with inline styles | `assert_csp_safe` on every new response |
| Viewer masking | Constraint | Desk search | Yes, if the viewer could search real names | `desk.suggest` reuses `queries._search` (06) |
| `status=confirmed` list tests | Direct | Derived filters | **Yes** if `confirmed` excluded ended bookings (`test_bookings.py:434,455,467`) | Additive filters (Decisions) |
| `parse_list_params`, `list_bookings` | Direct | Derived filters | Yes: `status` is checked against `Status.values`; no `now` | 06 validates against `STATUS_CHOICES`, adds `now`, passes it from `views.bookings_view` |
| `_render_fragment`, `_panel_message` | Direct | Desk responses | Yes: hard-wired to `schedule.html` and `#panel` | 08 adds keyword-only `template=SCHEDULE`; desk refusals retarget `#desk` |
| `queries.BookingDetail`, `schedule.BookingDetail` | Direct | Check in on detail and panel | Yes: no `can_check_in` | 06 adds it to `queries`; 09 to `schedule` |
| `dashboard/base.html` blocks | Direct | H1 block | Yes: `dashboard_title` already exists (line 15) | 07 names the H1 block `dashboard_heading` |
| Landing | Free tier | Free tonight | No, but it now wakes Neon | Accepted (Decisions) |

## Units
| Unit | Title | Category | Prompts | Depends | High-stakes | Acceptance criteria |
|---|---|---|---|---|---|---|
| CBS-18 | Storefront redesign | Changed | 01–04 | — | yes (04) | R1–R4: pages match the spec; Free tonight links into `/book`; no "sent to" on success; web suite green |
| CBS-19 | Check-in model and permission | Added | 05, 06 | — | yes | R5 R6: check-in rules and idempotency tested; viewer matrix tested |
| CBS-20 | Dashboard redesign and Front desk | Added | 07–11 | CBS-19 | no (code-guardian anyway: new write path) | R7 R8 R9: desk works with and without htmx; full-court blocks span both halves; CSP-safe; masked for the viewer |
| CBS-21 | Privacy notice and runbook | Changed | 12 | CBS-20 | no | R10: `/privacy` lists the check-in time; the runbook has the 0003 migration step |

Merge order: CBS-18 and CBS-19 can go in parallel, then CBS-20, then CBS-21. Each is a PR into `develop`.

**Release:** before the `develop → main` PR, the user applies migration 0003 with `MIGRATE_DATABASE_URL` (runbook, 12).

## Prompts
| # | Title | Unit | Model | Effort | Depends | Group |
|---|---|---|---|---|---|---|
| 01 | Web tokens, sport colours and the shell | CBS-18 | sonnet | medium | — | A |
| 02 | Landing: Free tonight, rates table, FAQ | CBS-18 | sonnet | medium | 01 | A |
| 03 | /book: step cards and sticky summary | CBS-18 | sonnet | high | 02 | A |
| 04 | Success, cancelled and Find booking pages | CBS-18 | opus | medium | 03 | A |
| 05 | Check-in columns, migration and service | CBS-19 | opus | high | — | B |
| 06 | can_check_in, desk queries, derived statuses | CBS-19 | opus | high | 05 | B |
| 07 | Dashboard shell: sidebar, tokens, fonts | CBS-20 | sonnet | medium | 06 | C |
| 08 | Front desk page and check-in action | CBS-20 | opus | high | 07 | C |
| 09 | Schedule block grid, now marker, panel check-in | CBS-20 | sonnet | high | 08 | C |
| 10 | Bookings list and detail restyle | CBS-20 | sonnet | medium | 09 | C |
| 11 | Overview restyle | CBS-20 | sonnet | medium | 10 | C |
| 12 | Privacy notice and runbook | CBS-21 | sonnet | medium | 11 | D |

Why opus:
- 04: `app/book/success/**`
- 05: models and migrations
- 06: `accounts/**`
- 08: a new write path with a permission and the viewer budget

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
- Sign in as the viewer: contact details are masked, name search matches demo bookings only, and checking in a real online booking returns a 403.

## Rollback
- Revert the unit's merge on `develop`, and on `main` if it's already released.
- Migration 0003 only adds nullable columns, so the old code ignores them. Leave the migration applied; a later contract plan can drop the columns.

## Log
- 2026-10-28: planned from the Claude Design handoff (prototypes `Kalaro Booking`, `Kalaro Staff`). Status draft; next step `/audit-plan`.
- 2026-10-28: audited (BLOCK → fixed), 12 fixes applied: additive derived filters, one `status_key` rule, no check constraint, `_search` reuse, overview reuse in `desk.py`, `_render_fragment(template=)`, `check_in` URL name, `can_check_in` on both details, `dashboard_heading`, 07 test files, demo seeding dropped (U4 → sonnet). Status audited.
- 2026-10-28: tickets: epic CBS-17; U1–U4 → CBS-18, CBS-19, CBS-20, CBS-21. Sprint 3 written to TASKS.md.
- 2026-10-28: CBS-18 started on branch CBS-18. Rollback point afcf34591d3a24785c88074f1f1e05c38875c3cf. Status in-progress.
- 2026-10-28: 01 done (sonnet, 0 retries): tokens, JetBrains Mono, sticky header and footer, `SPORT_COLORS` with a fixture drift test; web 178 tests green.
- 2026-10-28: 02 done (sonnet, 0 retries): landing rebuilt; `FreeTonight` (5 parallel `getAvailabilityOnce`, drops failed sports, null if none); rates `<table>`; FAQ `<details>`. Sport colour dots use an inline `style` (web CSP allows `'unsafe-inline'` styles; runtime value, not prototype CSS). Web 187 tests.
- 2026-10-28: user approved one extra file for CBS-18: `.prettierignore` ignores `docs/plans/**/prototypes/` (root `format:check` was red on `develop` since the Sprint 3 plan merge).
- 2026-10-28: 03 done (sonnet, 0 retries): four `StepCard`s, `BookingSummary` aside + bottom bar (total = server `slot.price_centavos`), `CourtPicker`, `SubmitOverlay`; `DetailsForm` loses its in-form summary and submit (Continue submits via `form="details-form"`; a `<fieldset disabled={pending}>` keeps the double-submit guard); `withFirstFreeCourt` picks a court for Free tonight's court-less links. Browser-checked by the agent at 1200 and 390px against a stub API.
- 2026-10-28: fixes after 03 (user: "fix the problems"), in the unit's files: sport swatches are `SPORT_BG` classes on `--color-sport-*` tokens (no inline styles; drift test vs `SPORT_COLORS`); landing shares one `cache(getCatalog)` between Rates and `FreeTonight` (`loadCatalog` prop); `/book`'s bottom bar no longer covers the footer (`body:has(.book-bar)` padding). Stray pre-audit plan copy under `2026-10-22-portfolio-ready/prompts/` deleted (bookkeeping). Web 188 tests.
- 2026-10-28: 04 done (opus, 0 retries): success/cancelled/`/booking` restyled; dark reference card with `CopyReference` (no "sent to"); success data path byte-identical (only the Sport/Coverage rows merged and Time shows the length). Fix after verify: the lookup's typo hint matched `lookup.ts`'s message string, so it became always-on helper text under the reference input. Web 191 tests.
- 2026-10-28: CBS-18 shipped as PR #23 (66d4bb0), CI green. Gate: CI + code-guardian → 0 Blockers; fixed in 6c97c6b: pending-submit guard on the external Continue, Free tonight peak label from the server's flag on the earliest start, solid focus rings, stale-start notice, 84px bar room. Not fixed (follow-ups): no server-render tests for `/book` (`withFirstFreeCourt`, `BookingSummary`, `priceLines`, tile court choice); footer copy hard-coded rather than from `SITE.testModeNotice`; Free tonight wording before 07:00 and after 22:00; `copy-reference.test.tsx` fakes React hooks (no DOM env). CI green on 6c97c6b.
- 2026-10-28: CBS-18 merged (PR #23). Next unit: CBS-19.
- 2026-10-28: CBS-19 started on branch CBS-19. Rollback point 854dfc8ffbeceedaf9276fbda998a7a63c23a07e.
- 2026-10-28: 05 done (opus, 0 retries): `checked_in_at`/`checked_in_by` + expand-only 0003; `checkin.check_in` re-reads under `select_for_update`, already-checked-in returns False before the date rules; 15 tests incl. a MigrationExecutor 0002↔0003 test. Bookings 136 tests.
- 2026-10-28: 06 done (opus, 0 retries): `roles.can_check_in` (mirrors `check_in`; a test pins owner `can_check_in` ⇔ `check_in` succeeds); `queries.status_key`, additive `checked_in`/`completed` filters (blocks excluded), `now` on `list_bookings`/`_row`, `can_check_in` on `BookingDetail`; `desk.py` lookup/suggest/arriving/on_court/stats reusing `_search` and the overview aggregates. Agent calls to review: spec demo ref `KC-W3PE7U` has a non-alphabet U (tests use `W3PE7V`); suggestions are today-and-later, not `KC-`-normalised; "spaces in use" counts online + walk-in locks only. Backend 871 tests.
- 2026-10-28: CBS-19 shipped as PR #24 (4dc2d5b), CI green. Gate: CI + code-guardian → 0 Blockers (APPROVE WITH NITS). Fixed in e685eb9 (user: Should-fixes + nits): blocks get no desk warning and an empty amount; a lapsed pending hold says "the hold has lapsed"; `suggest` needs 2 chars server-side; `on_court` requires `starts_at <= now` and `arriving` keeps an early check-in (shown checked in) until it starts — a deviation from the spec's "Arriving: not checked in", so no row vanishes from both lists; `NEEDS_REFUND` added to the refused cases. Not fixed: `normalise_query` look-alikes (O→0, I/L→1) and `KCW3PE7V`. Notes for CBS-20: the check-in view must gate on `can_check_in` (403) but treat already-checked-in as a no-op success (a double-click), and mask the toast name with `name_for`. Release must not ship before CBS-21 (`/privacy` lists the check-in time). CI green on e685eb9.
- 2026-10-28: CBS-19 merged (PR #24). Next unit: CBS-20.
- 2026-10-28: CBS-20 started on branch CBS-20. Rollback point 787106e04946e91fab33f852cff5335b0448bd95.
- 2026-10-28: 07 done (sonnet, 0 retries): sidebar shell (`dash-side`, Front desk guarded by `{% url ... as %}`, `dashboard_nav_badge`), `dashboard_eyebrow`/`dashboard_heading` blocks, `body_class`/`main_class` hooks in `templates/base.html`, self-hosted Archivo variable + JetBrains Mono Bold (OFL), tokens, buttons, pills, sport tags, CSS-only toast. Pages show two H1s until 08–11 set `dashboard_heading`. Backend suite green; image builds with no env.
- 2026-10-28: 08 done (opus, 0 retries): `desk/`, `desk/suggest/` (`desk_suggest`), `desk/check-in/<ref>/` (`check_in`); `_render_fragment(template=)`; already-checked-in is a no-op success before `can_check_in`; `CHECK_IN_ERRORS` per code; OOB toast (name via `name_for`) and OOB nav badge (`#desk-badge`, beyond the brief); a not-found GET lookup also lists name matches (works without JS). 37 view tests in new `test_desk.py` (query tests are `test_desk_queries.py`). Follow-ups: a non-JS desk refusal renders in `fragment_page.html` (titled Schedule, out of scope); "View in schedule" cannot open the panel. Backend 916 tests.
- 2026-10-28: 09 done (sonnet, 1 resume after a session rate limit, 0 retries): `.sg` block grid (one block per booking; `row_span` = rows the booking holds, so full basketball spans both halves), literal `.r-/.c-/.rs-/.cs-/.now-m-*` utilities, now marker today only, `block_state` from `queries.status_key`; `schedule.BookingDetail` gets `can_check_in`, `status_key`, `checked_in_clock` and a derived `status` label; `check_in_view` `return=schedule|detail`, refusals for both via `_panel_message`. Removed dead `Cell.css`/`_SLOT_CLASSES`, `Grid.hours` → `hour_heads`, old `.schedule/.slot-*/.swatch` CSS. Panel stays in-flow (no fixed drawer or close, needs JS); no live price line. Backend 968 tests.
- 2026-10-28: 10 done (sonnet, 0 retries): `bk-toolbar` (status `.seg` radios over all 7 `STATUS_CHOICES`, works without JS), one-link rows, sport tags, `pill-{status_key}`; footer "Showing n of total" (range dropped); detail key/value cards with Check in (`return=detail`, also `hx-post` to `#panel` like Cancel) and a Checked in row. Pill labels for derived states come from an `{% if %}` chain repeated 3 times (no derived label on `queries` rows; follow-up). **Found:** `test_bookings.Tags` had no `handle_starttag`, so `assert_csp_safe` (also imported by `test_desk.py`) checked nothing since it was written; fixed, all responses pass. Old `.badge*`, `.filters*`, `.details-wide` CSS removed. Backend 988 tests.
- 2026-10-28: 11 done (sonnet, 0 retries): overview restyled (4 `.stat` cards, per-sport `ov-fill` bars on the existing `SportRevenue.width`, revenue table, heatmap, next 3 hours); only Python change `HeatCell.level` 0–5 → 0–9 (`min(9, pct // 10)`, sole reader `overview.html`). Left out (no source, no new SQL): week-over-week (`_revenue` has no prior-week window) and the spec's 7-day bookings/walk-ins, 7-day utilization/peak and average-booking cards; cards show Revenue 7d, Bookings today, Utilization today, Active holds. Note: white text from `.heat-6` per spec may be low contrast. Backend 994 tests.
- 2026-10-28: CBS-20 shipped as PR #25 (bc4eb1a), CI green. Gate: CI + code-guardian → 0 Blockers (APPROVE WITH NITS). Fixed in 5af39f1 (user: Should-fix + nits): the viewer gets 403 on an already-checked-in real online booking (the no-op success now applies R6 inline in `views.py`); the desk name fallback (block → Blocked, live nameless → Walk-in, else —; `DeskRow` has no `source`, so an ended anonymized walk-in shows —); `.sg-now` spans 24 rows; unstyled `dash-head`/`desk-suggest` dropped, `ov-bar-label` styled; dead CSP assertion removed; viewer-masking tests for the full desk page and the no-JS name path. CI green on 5af39f1.
- 2026-10-28: CBS-20 merged (PR #25). Next unit: CBS-21.
