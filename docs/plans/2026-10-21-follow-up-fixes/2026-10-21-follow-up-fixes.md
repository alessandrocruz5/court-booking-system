---
type: plan
kind: feature
status: draft
repo: court-booking-system
delivery: pr
base: main
sprint: 2
epic:
created: 2026-10-21
risk: high
prompts: 11
graph_built: none
tags: [plan]
---
# Follow-up fixes: Sprint 1's deferred items, triaged

## Request
> the follow up fixes

That means the "Follow-ups (not scheduled)" and "Deferred" notes on the Sprint 1 units in `TASKS.md`. The user
chose the **triaged set** (2026-10-21): review-constraint gaps, compliance drift tests, user-visible defects,
and the duplicates that can drift into bugs. Pure perf, CI-hardening and wording nits are left out. The user
also made these calls: N7 means "the viewer cancels only bookings that haven't ended", N8 means "preset reasons
for viewer blocks", the two-tab cookie is fixed with "a ref in the URL picks the visitor's own entry", and the
nightly advisory lock is "dropped, with a runbook note".

| # | Requirement | Source |
|---|---|---|
| R1 | Every `/api/v1/*` and `/webhooks/*` response sends `Cache-Control: no-store`. That includes an unmatched-route 404 and a 400/413/500 raised outside a view. | CBS-5, CBS-6 Deferred; review constraint |
| R2 | gunicorn creates no control socket. | CBS-3 follow-up |
| R3 | IP normalisation exists once: `storefront.views` uses `core.http`'s. | CBS-9 follow-up |
| R4 | Expiring a checkout session exists once: the dashboard's cancel uses `payments.confirm`'s helper. | CBS-10 follow-up |
| R5 | When a PayMongo checkout session was created but saving its ID failed, that session is expired as well as the hold being released. | CBS-6 Deferred |
| R6 | The demo viewer can cancel only bookings that haven't ended. The owner is unchanged. | CBS-10 N7 |
| R7 | A NUL byte in a dashboard reference URL or in `?court=` gives a 404, not a 500. | CBS-10 N1 |
| R8 | The viewer's write budget is charged only by a create that passes form validation. | CBS-10 N2 |
| R9 | A dashboard fragment endpoint asked without htmx answers with a full page (with the banner) or a redirect to one, never a bare fragment. | CBS-10 N4 |
| R10 | The viewer chooses a block's note from a fixed list; the owner keeps free text. | CBS-10 N8 |
| R11 | The overview's refund alert names no cause, because a staff cancel now also produces `needs_refund`. | CBS-10 follow-up |
| R12 | Drift tests: every rate-limit window ≤ `nightly.RATE_LIMIT_MAX_AGE`; the backend `RETENTION_DAYS` equals the web's; a test pins the 10-minute prune boundary. | CBS-8 follow-ups, CBS-10 N3 |
| R13 | The runbook says to check that no `cb-nightly` execution is running before executing it by hand. | CBS-8 follow-up (advisory lock; user choice) |
| R14 | The `/book/success` `needs_refund` copy names no cause. | CBS-10 follow-up |
| R15 | The (defensive) bad-checkout-URL branch of `startCheckout` releases the hold it just made. | CBS-7 follow-up |
| R16 | With two checkouts open in one browser, each tab's success and cancel page acts on its own session. | CBS-7 follow-up |

## Context used
- `TASKS.md` Sprint 1, every unit's **Downstream**: the follow-up and deferred lists (lines 31, 41, 49, 57, 66, 76, 87, 93), the env-key four-places rule (CBS-3), `PayMongoClient` never inside `atomic()` (CBS-5), the "Invalid requests don't count against the rate limits" convention (CBS-6), `CHECKOUT_COOKIE` defined twice (CBS-7), and the dashboard view conventions (CBS-9).
- `docs/plans/2026-10-16-court-booking-mvp/2026-10-16-court-booking-mvp.md` `## Decisions`: the locked rule "The viewer can operate the demo … cancel demo or staff-made bookings" (narrowed here by R6, user choice), the Neon pooler (transaction mode), and the non-goals. `## Log` 2026-10-21 holds the code-guardian nit list N1–N8. N5 and N6 are already fixed in bc28534.
- `CLAUDE.md` `## Review constraints`, `## High-stakes paths`, `## Hidden coupling` (checkout cookie; test DB seed data).
- Graph: none (`graphify-out/` is absent), so blast radius came from grep.
- Code:
  - `apps/backend/config/settings.py` `MIDDLEWARE`: no outermost header middleware. `storefront/auth.py:24-57` and `payments/views.py:30-38` set no-store per view only. `config/urls.py:7-8` mounts `webhooks/` and `api/v1/`.
  - `apps/backend/config/gunicorn.conf.py`: no `control_socket_disable`. gunicorn 26.2.0 has `ControlSocketDisable` (since 25.1.0).
  - `apps/backend/core/http.py:19-30` (`_normalise`) is identical to `storefront/views.py:131-145` (`_client_ip`), which is called at :236 and :377.
  - `apps/backend/payments/confirm.py:202-209` (`_expire_session`, called at :231) is identical to `dashboard/views.py:177-185` (`_expire_checkout`, called at :204). `dashboard/tests/test_schedule.py:137-140` patches `views.get_client`.
  - `apps/backend/storefront/views.py:288-309`: when `booking.save` fails after `create_checkout_session`, the hold is released but the session stays open. There's no `ATOMIC_REQUESTS`. `storefront/tests/test_bookings_api.py:33-69` (`FakePayMongo`, `use_fake_paymongo`), :164-165 (success/cancel URL asserts).
  - `apps/backend/accounts/roles.py:44-53` (`can_cancel`, no time check); callers `dashboard/schedule.py:171,252`, `dashboard/queries.py:623`, `dashboard/views.py:195`, `accounts/tests/test_access.py:140-157`. Dashboard tests pin `NOW = 2026-11-02 12:00` through `views.timezone`, so `now` must be threaded through rather than read inside `roles`.
  - `apps/backend/dashboard/schedule.py:228-230` and `dashboard/queries.py:614-616` look up `reference` unchecked (the `<str:reference>` paths in `dashboard/urls.py`); `forms.StaffBookingForm.for_cell` queries `court_code` unchecked. `queries.py:419-420` has the NUL pattern to copy.
  - `apps/backend/dashboard/views.py:247-252` (`_create`) charges the budget before `form.is_valid()`.
  - `dashboard/views.py` `booking_panel`, `new_view`, `cancel_view`, `_panel_message`, `_form_response`, `_grid_response` return partials whatever the request. `dashboard/templates/dashboard/schedule.html` holds the partials `grid`, `panel` and `form` (with `{% csrf_token %}`).
  - `apps/backend/dashboard/forms.py:84` (`note` free text); `bookings/demo.py:72-78` (`BLOCKS` reasons); `queries.py:620-622` (a block's note is shown to everyone).
  - `apps/backend/dashboard/templates/dashboard/overview.html:15`; `dashboard/tests/test_overview.py:450`.
  - `apps/backend/bookings/management/commands/nightly.py:33-37` (`RETENTION_DAYS`, `RATE_LIMIT_MAX_AGE`); `apps/web/src/content/site.ts:34`; `storefront/views.py:46`, `dashboard/views.py:39-40`, `accounts/views.py:30` (the windows); `accounts/tests/test_login.py:238` (the only drift test so far); `core/ratelimit.py:54-59` (`prune` uses `<`); `turbo.json` (test inputs).
  - `apps/web/src/lib/booking/actions.ts` (`startCheckout`, `releaseHold`, the `CHECKOUT_COOKIE` set), `app/book/success/page.tsx`, `app/book/cancelled/page.tsx`, `app/book/__tests__/result-pages.test.tsx`, `src/lib/booking/__tests__/actions.test.ts` (session IDs like `cs_test_abc`).
  - `apps/backend/payments/paymongo.py:25` (`CHECKOUT_SESSION_ID = ^cs_[A-Za-z0-9]+$`); `bookings/references.py` (`KC-` plus 6 Crockford base32 characters).

## Options
**Two tabs sharing `cb_checkout` (R16)**

| Option | Cost | Time | Risk | Maintenance | Compliance |
|---|---|---|---|---|---|
| A. The backend's success/cancel URLs carry `?ref=`, and the cookie holds up to 3 `REF.session` entries; `ref` only picks among them | 3 opus prompts | ~1 day | Medium: it touches the payment-result path | One small cookie module | Status still comes only from the server; the constraint wording gets a one-line clarification |
| B. Defer and document | 0 | 0 | None | None | None |

**Recommendation:** A, because cancelling in one tab today releases the other tab's hold and expires its session.
**Chosen:** A (user, 2026-10-21).

**Nightly concurrent-run guard (CBS-8 follow-up)**

| Option | Cost | Time | Risk | Maintenance | Compliance |
|---|---|---|---|---|---|
| A. Drop it and add a runbook note | 1 doc line | minutes | Overlap needs a manual execute during the 03:00 run, and the cost is a partial demo reseed repaired the next night | None | None |
| B. `ratelimit.hit` as a once-per-window guard | Small | hours | Two runs straddling a fixed-window boundary both proceed | Low | None |
| C. A lock table plus a migration | Medium | ~1 day | Low | A table and its grants; the migration is run by hand | None |

**Recommendation:** A, because session advisory locks don't hold through Neon's transaction-mode pooler, and the
run spans many transactions. **Chosen:** A (user, 2026-10-21).

## Decisions
- **Triaged scope** (user, 2026-10-21), as listed in Request.
- **No-store is enforced once, outermost** (R1): `core.middleware.NoStoreMiddleware` is first in `MIDDLEWARE`, so it also covers responses produced by the URL resolver's 404, by `DisallowedHost`/`RequestDataTooBig` in other middleware, and by the 500 handler. The per-view decorators stay as defence in depth.
- **The viewer's cancel rule** (R6, user choice, narrowing a locked decision): the viewer may cancel a pending or confirmed demo booking, walk-in or block **that hasn't ended** (`ends_at > now`). `can_cancel` takes a required keyword `now`, so every caller passes the request's (testable) clock.
- **NUL in a lookup key** (R7): `schedule.get_booking`, `queries.get_booking` and `StaffBookingForm.for_cell` return None for a value containing `\x00`, following `queries.py:419-420`. The URL patterns stay `<str:reference>`.
- **Budget after validation** (R8): `_create` validates the form first, then charges the budget, then checks `DEMO_LIVE_CAP`. `cancel_view` already checks `can_cancel` before the budget.
- **Non-htmx fragments** (R9): a GET of a fragment redirects to its full page (the panel goes to `booking_detail`; the add form goes to the schedule for that day). A successful POST redirects with 303 to the schedule for that day. A refusal or form error renders `dashboard/fragment_page.html`, which extends `dashboard/base.html` and includes the named partial with the same status. htmx responses are unchanged.
- **Viewer block reasons** (R10, user choice): `forms.BLOCK_REASONS = ("Maintenance", "Resurfacing", "Coaching clinic", "League night", "Private event")`, a superset of `demo.BLOCKS`. With `preset_notes=True` (the viewer), the `note` field is a `ChoiceField` of those, so validation happens on the server. The owner's form is unchanged.
- **Cause-neutral refund copy** (R11, R14): the dashboard alert and the success page say a refund is due, not why.
- **Drift tests** live in `bookings/tests/test_nightly.py` (R12). The backend test reads `apps/web/src/content/site.ts` at run time (`Path(settings.BASE_DIR).parent.parent`, as in `storefront/tests/test_contract.py:24`), and `turbo.json`'s test inputs add that file so the backend tests re-run when it changes.
- **Checkout cookie v2** (R16): `apps/web/src/lib/booking/checkout-cookie.ts` (a plain module, not `"use server"`) owns `CHECKOUT_COOKIE` (ending the duplicate CBS-7 noted) and the helpers.
  - The value is `REF.sessionId` entries joined by `|`, newest first, at most 3. A legacy bare `cs_…` value still parses, as an entry with no reference.
  - `?ref=` with a well-formed reference selects that entry, or none if it isn't there (never another booking's session). Without a valid `ref`, the newest entry is used.
  - The backend's success/cancel URLs add `?ref=<reference>`. If PayMongo ever drops the query string, the newest-entry fallback gives today's behaviour.
  - Payment status still comes only from `checkout/confirm`/`release`.
- **Deploy order:** every unit deploys on its own. In U5, the backend's `?ref=` is ignored by an old web build, and a new web build without `ref` falls back to the newest entry.

**Non-goals:** the SlotLock/occupancy/prune indexes (a laptop migration, and demo scale doesn't need them); digest-pinned base images; Dependabot major/minor ignores; `BACKEND_HOST` trailing slash; `run.developer` instead of `run.admin`; a JSON 405 on the webhook; a `/48` rate-limit bucket; `docs/api/README.md` `BookingSummary.sport` nullability; `releaseHold`'s redundant second release; the "never changed" wording, demo halves ratio, `clear_sessions` clock and `seed_demo` print nits; `_is_reference_clash` duplication; the nightly advisory lock (replaced by R13); the Dockerfile's "control socket" home-dir comment (the home dir stays and is harmless); verifying `clientIpFrom` on Cloud Run (covered by the existing pre-release checklist).

## Change list
| File | Action | Why | Req | Prompt |
|---|---|---|---|---|
| `apps/backend/core/middleware.py` | C | `NoStoreMiddleware` | R1 | 01 |
| `apps/backend/core/tests/test_no_store.py` | C | 404/400 no-store on `/api/v1/*` and `/webhooks/*`; other paths untouched | R1 | 01 |
| `apps/backend/config/settings.py` | M | Middleware first in `MIDDLEWARE` | R1 | 01 |
| `apps/backend/config/gunicorn.conf.py` | M | `control_socket_disable = True` | R2 | 02 |
| `apps/backend/core/http.py` | M | `_normalise` → public `normalise_ip` | R3 | 02 |
| `apps/backend/storefront/views.py` | M | Use `normalise_ip` (02); expire an orphaned session (03); `?ref=` in success/cancel URLs (09) | R3 R5 R16 | 02, 03, 09 |
| `apps/backend/payments/confirm.py` | M | `_expire_session` → public `expire_session` | R4 | 03 |
| `apps/backend/dashboard/views.py` | M | Use `expire_session` (03); thread `now` (04); budget after validation (05); non-htmx responses (06); `preset_notes` (07) | R4 R6 R8 R9 R10 | 03–07 |
| `apps/backend/dashboard/tests/test_schedule.py` | M | Patch `confirm.get_client` (03); tests for R6–R10 | R4 R6–R10 | 03–07 |
| `apps/backend/storefront/tests/test_bookings_api.py` | M | Orphaned-session test (03); `?ref=` URL asserts (09) | R5 R16 | 03, 09 |
| `apps/backend/accounts/roles.py` | M | `can_cancel(..., *, now)`: viewer only before `ends_at` | R6 | 04 |
| `apps/backend/accounts/tests/test_access.py` | M | `can_cancel` cases with `now` | R6 | 04 |
| `apps/backend/dashboard/schedule.py` | M | Pass `now` (04); NUL guard in `get_booking` (05) | R6 R7 | 04, 05 |
| `apps/backend/dashboard/queries.py` | M | `get_booking(now=)` (04); NUL guard (05) | R6 R7 | 04, 05 |
| `apps/backend/dashboard/forms.py` | M | NUL guard in `for_cell` (05); `BLOCK_REASONS`, `preset_notes` (07) | R7 R10 | 05, 07 |
| `apps/backend/dashboard/tests/test_bookings.py` | M | Detail-page NUL 404 | R7 | 05 |
| `apps/backend/dashboard/templates/dashboard/fragment_page.html` | C | Full-page wrapper for a partial | R9 | 06 |
| `apps/backend/dashboard/templates/dashboard/overview.html` | M | Cause-neutral alert | R11 | 07 |
| `apps/backend/dashboard/tests/test_overview.py` | M | Alert copy assert | R11 | 07 |
| `apps/backend/bookings/tests/test_nightly.py` | M | Drift tests and the prune boundary | R12 | 08 |
| `turbo.json` | M | Test inputs add `apps/web/src/content/site.ts` | R12 | 08 |
| `docs/runbook.md` | M | `## Demo data and nightly job`: check for a running execution before a manual execute | R13 | 08 |
| `apps/web/src/lib/booking/checkout-cookie.ts` | C | Cookie name and entry helpers | R16 | 10 |
| `apps/web/src/lib/booking/__tests__/checkout-cookie.test.ts` | C | Helper tests | R16 | 10 |
| `apps/web/app/book/success/page.tsx` | M | Pick the session by `ref`; neutral `needs_refund` copy | R14 R16 | 10 |
| `apps/web/app/book/cancelled/page.tsx` | M | Pick the session by `ref`; the form posts `ref` | R16 | 10 |
| `apps/web/app/book/__tests__/result-pages.test.tsx` | M | Two-entry and `ref` tests; copy | R14 R16 | 10 |
| `apps/web/src/lib/booking/actions.ts` | M | Write v2 entries; release on a bad URL; `releaseHold(formData)` by `ref` | R15 R16 | 11 |
| `apps/web/src/lib/booking/__tests__/actions.test.ts` | M | Tests for the above | R15 R16 | 11 |
| `CLAUDE.md` | M | Hidden-coupling cookie line; one-line `?ref=` clarification under "Payment status" | R16 | 11 |

## Blast radius
**Risk:** high: it touches `payments/**`, `storefront/views.py`, `accounts/**`, `config/settings.py`, `apps/web/src/lib/booking/actions.ts` and `app/book/success/**`, the payment-result path.

| Affected | Kind | Via | Breaks? | Mitigation |
|---|---|---|---|---|
| Every backend request | Direct | New outermost middleware | No: it only sets a header on `/api/` and `/webhooks/` paths | 01 tests that `/` is untouched; CI `images` smoke run |
| `storefront.auth.require_service_token`, `payments.views._no_store` | Direct | Same header set twice | No: same value | Kept as defence in depth |
| `core.http.client_ip` | Direct | `_normalise` renamed | No: same body | Existing `accounts/tests/test_access.py` `test_client_ip` cases |
| `storefront.views.create_booking`, `booking_lookup` | Direct | `_client_ip` → `normalise_ip` | No: identical logic | `test_bookings_api.py` zone-ID and IPv6 /64 tests, `test_checkout_api.py:317-327` |
| `payments.confirm.release_checkout` | Direct | `_expire_session` renamed | No | `payments/tests/test_confirm.py:560-640` |
| `dashboard/tests/test_schedule.py` `mock_client` | Non-graph | Patches `views.get_client`, which 03 removes | **Yes** | 03 repoints it to `payments.confirm.get_client` |
| `storefront.views.create_booking` failure branches | Direct | Extra best-effort HTTP call | No: outside any transaction, never raises | 03 test: save fails → session expired, hold released |
| `accounts.roles.can_cancel` callers (`schedule.py:171,252`, `queries.py:623`, `views.py:195`, `test_access.py`) | Direct | New required `now` | **Yes** until updated | 04 updates every caller; grep check in Done when |
| `schedule.booking_detail`, `queries.get_booking` callers (views, `test_bookings.py:308,600`) | Direct | New optional `now` | No: defaults to `timezone.now()` | — |
| Viewer UX: cancelling a past real walk-in/block | Behaviour | R6 | Intended | Owner unchanged; test both |
| Dashboard tests that call fragment endpoints without `HX` | Non-graph | R9 changes non-htmx responses | Possibly (the suite uses `headers=HX` throughout, `test_schedule.py:24`) | 06 runs the full dashboard suite and updates only tests that asserted bare-fragment behaviour |
| `cancel_view` `return=detail` (`test_bookings.py:752`) | Direct | R9 | No: that branch is unchanged | — |
| `StaffBookingForm` callers | Direct | New `preset_notes` kwarg | No: defaults to False | — |
| `seed_demo` block notes | Non-graph | R10 reasons list | No: `BLOCK_REASONS` ⊇ `demo.BLOCKS` notes | 07 test asserts the superset |
| Viewer create test fixtures (`form_data(kind="block", note=…)`) | Non-graph | R10 | Possibly: a viewer test posting a free-text block note now fails validation | 07 updates those tests to use a listed reason |
| `turbo.json` test cache | Non-graph | New input | No: it only widens invalidation | — |
| PayMongo redirect (`success_url`/`cancel_url`) | Non-graph (external) | `?ref=` query | Unverified: PayMongo is expected to keep the query string | Fallback to the newest entry; E2E manual check on test mode |
| Contract fixtures / `schemas.ts` | Non-graph | — | No: no API body changes | — |
| `cb_checkout` readers (`app/book/{success,cancelled}`) | Hidden coupling | Format v2 | **Yes** if the writer changed first | 10 (readers accept v1 and v2) runs before 11 (writer); CLAUDE.md updated in 11 |
| `/privacy` | Compliance | — | No: the cookie holds booking references and session IDs, no personal data; storage and retention are unchanged | — |

**Known risks in the touched area:** `check_checkout` raises inside `atomic()`, so API tests stay transactional with `serialized_rollback=True` (CBS-5). The PayMongo client is never used inside `atomic()`. Turbo strict env mode is unaffected (no new env). The CSRF-failure 403 swaps into the target (CBS-10 log). `seed_staff` deletes every session (unaffected).

## Units
| Unit | Title | Category | Prompts | Depends | High-stakes | Acceptance criteria |
|---|---|---|---|---|---|---|
| U1 | API no-store and backend hygiene | Fixed | 01, 02 | — | yes | R1: an unmatched `/api/v1/x` 404 and a disallowed-host `/webhooks/paymongo` 400 send `no-store`. R2: the gunicorn config sets `control_socket_disable = True`. R3: no `_client_ip`/`_normalise` remains. |
| U2 | One checkout-session expiry, including orphaned sessions | Fixed | 03 | U1 | yes | R4: `dashboard/views.py` has no PayMongo client code of its own. R5: a failed session-ID save releases the hold and expires the session. |
| U3 | Dashboard hardening | Fixed | 04, 05, 06, 07 | U2 | yes | R6: the viewer's cancel of an ended walk-in is 403. R7: NUL references and `?court=` give 404. R8: invalid viewer creates don't use up the budget. R9: no bare fragment without htmx. R10: the viewer's block note must be a listed reason. R11: the alert names no cause. |
| U4 | Drift tests and nightly runbook note | Changed | 08 | — | no | R12: three drift/boundary tests pass and fail on a mismatched constant. R13: the runbook line exists. |
| U5 | Checkout per-tab sessions and result copy | Fixed | 09, 10, 11 | U2 | yes | R14: the neutral `needs_refund` copy. R15: a bad URL releases the hold. R16: two entries, and `?ref=` picks each tab's own session on success and cancel. |

Merge order: U1 → U2 → U3 → U4 → U5. Each unit deploys on its own against `main`.

## Prompts
| # | Title | Unit | Model | Effort | Depends | Group | Files |
|---|---|---|---|---|---|---|---|
| 01 | No-store middleware for `/api/` and `/webhooks/` | U1 | opus | high | — | A | core/middleware.py, core/tests/test_no_store.py, config/settings.py |
| 02 | gunicorn control socket off; one IP normaliser | U1 | opus | medium | 01 | A | config/gunicorn.conf.py, core/http.py, storefront/views.py |
| 03 | One checkout-session expiry; expire orphaned sessions | U2 | opus | high | 02 | B | payments/confirm.py, dashboard/views.py, dashboard/tests/test_schedule.py, storefront/views.py, storefront/tests/test_bookings_api.py |
| 04 | Viewer cancels only bookings that haven't ended | U3 | opus | high | 03 | C | accounts/roles.py, accounts/tests/test_access.py, dashboard/schedule.py, dashboard/queries.py, dashboard/views.py, dashboard/tests/test_schedule.py |
| 05 | NUL-byte 404s; viewer budget after validation | U3 | sonnet | medium | 04 | C | dashboard/schedule.py, dashboard/queries.py, dashboard/forms.py, dashboard/views.py, dashboard/tests/test_schedule.py, dashboard/tests/test_bookings.py |
| 06 | Full pages, never bare fragments, without htmx | U3 | sonnet | high | 05 | C | dashboard/templates/dashboard/fragment_page.html, dashboard/views.py, dashboard/tests/test_schedule.py |
| 07 | Viewer block reasons; neutral refund alert | U3 | sonnet | medium | 06 | C | dashboard/forms.py, dashboard/views.py, dashboard/templates/dashboard/overview.html, dashboard/tests/test_schedule.py, dashboard/tests/test_overview.py |
| 08 | Drift tests, prune boundary, nightly runbook note | U4 | haiku | low | — | D | bookings/tests/test_nightly.py, turbo.json, docs/runbook.md |
| 09 | Success and cancel URLs name the booking | U5 | opus | medium | 03 | E | storefront/views.py, storefront/tests/test_bookings_api.py |
| 10 | Checkout cookie module; result pages pick their own session | U5 | opus | high | 09 | E | src/lib/booking/checkout-cookie.ts (+ test), app/book/success/page.tsx, app/book/cancelled/page.tsx, app/book/__tests__/result-pages.test.tsx |
| 11 | `startCheckout` writes per-booking entries; bad-URL release; `releaseHold` by ref | U5 | opus | high | 10 | E | src/lib/booking/actions.ts, src/lib/booking/__tests__/actions.test.ts, CLAUDE.md |

Paths are under `apps/backend/` for 01–09 (except `turbo.json` and `docs/runbook.md`, at the repo root) and under
`apps/web/` for 10–11 (except `CLAUDE.md`). Prompts in one unit run in order on one branch, so no two prompts run in
parallel.

Why opus:
- 01: `config/settings.py` is high-stakes, and middleware order decides which errors get covered.
- 02: `storefront/views.py` is high-stakes (the change is mechanical; effort medium).
- 03: `payments/**` and `storefront/views.py`; it adds an HTTP call that must stay outside any transaction.
- 04: `accounts/**` (permissions) and a locked decision; the signature change ripples through every `can_cancel` caller.
- 09: `storefront/views.py`; it changes the PayMongo redirect URLs.
- 10: `app/book/success/**`; the payment-result page picks which session to confirm.
- 11: `src/lib/booking/actions.ts`; it writes the cookie that the result pages trust.

## End-to-end verification
```bash
# CLAUDE.md ## Commands, from the repo root, in order:
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend

# R1
cd apps/backend && uv run pytest core/tests/test_no_store.py -q && cd ../..
# R2
cd apps/backend && uv run python -c "import runpy; assert runpy.run_path('config/gunicorn.conf.py')['control_socket_disable'] is True" && cd ../..
# R3 R4: no duplicates left (both print nothing)
grep -rn --include='*.py' -e '_client_ip\b' -e 'def _normalise' apps/backend
grep -rn --include='*.py' -e '_expire_checkout' -e '_expire_session' apps/backend
# R5 R16 (backend)
cd apps/backend && uv run pytest storefront/tests/test_bookings_api.py -q && cd ../..
# R6–R11
cd apps/backend && uv run pytest accounts dashboard -q && cd ../..
# R12
cd apps/backend && uv run pytest bookings/tests/test_nightly.py -q && cd ../..
# R13
grep -n 'executions list' docs/runbook.md
# R14–R16 (web)
pnpm --filter @cb/web test

# Manual, test mode, after U5 deploys (add to the pre-release run):
#   open two tabs on $WEB_URL/book, start a checkout in each (two different courts), cancel in tab A:
#   tab A shows "No worries", tab B's PayMongo page still pays, and tab B lands on its own confirmed reference
#   (the URL shows ?ref=<B's reference>). Every page still shows "Fictional venue · Test mode, no real payments".
#   curl -sI "$BACKEND_URL/api/v1/nope" | grep -i 'cache-control: no-store'
```

## Rollback
Each unit is one PR with no migration, env key or contract change, so `git revert` of its merge commit and a redeploy
(runbook `## Roll back`) restores the previous behaviour. Reverting U5 leaves v2 cookies in visitors' browsers, which
the old readers treat as an unknown session (`not_found`, or "released" on the cancel page) until they expire within
a day. That's acceptable on a test-mode demo.

## Log
- 2026-10-21: planned (triaged scope, N7 = not ended, N8 = preset reasons, two-tab = ref picks own entry, nightly lock dropped: user choices).
