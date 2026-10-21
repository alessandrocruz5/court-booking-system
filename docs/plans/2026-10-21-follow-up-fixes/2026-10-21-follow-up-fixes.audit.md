# Audit: [[2026-10-21-follow-up-fixes]]

## Audit 2026-10-21: BLOCK
Graph built: none (grep only) · Symbols traversed: 14 · Missed blast-radius items: 3

Request addendum (user, in the audit command): "make sure also to point to develop now instead of main".

| Sev | Check | Finding | Evidence | Fix |
|---|---|---|---|---|
| BLOCK | Unit shape | The plan targets `main` (frontmatter `base: main`; Units: "Each unit deploys on its own against `main`"), but the user now wants `develop`. `develop` exists **only locally**, so no PR can target it until it's pushed. | `git branch -a`: `develop` is listed, `origin/develop` isn't; `develop` = `main` = cc3d621 | Set `base: develop`. Before U1's branch, the user runs `git push -u origin develop`. Change every "against `main`" line in the plan to `develop`. |
| FIX | Usability | With `develop` as the base, merging a unit **never deploys**: Deploy runs only after CI on a push to `main`, and WIF accepts only `main`. So the plan's manual E2E step ("after U5 deploys") and its Rollback ("revert … and a redeploy") can't happen as written. | `.github/workflows/deploy.yml:7-10` (`workflow_run … branches: [main]`); `docs/runbook.md:218-224` | Add a **Release** step after U5: a `develop → main` PR, merged by the user, which deploys. Move the manual test-mode checks to after that merge. Rollback: revert on `develop`, and also on `main` if it was already promoted. |
| FIX | Notes & constraints | The profile still says `Base branch: main`. The plan's frontmatter wins for this plan, but the next `/plan-feature` (and anything that reads the profile) would go back to `main`. | `CLAUDE.md:21` | The user changes `CLAUDE.md` `## Workflow` to `- Base branch: develop`, committed with the ledger on `develop`. It isn't part of a unit. |
| FIX | Breakage | **Rollout gap in U5.** `pickCheckout` returns nothing when a valid `ref` isn't in the cookie, which also drops a legacy entry (no reference). Deploy rolls out `cb-backend` before `cb-web`, so a checkout started in between gets a `?ref=` URL (new backend) and a legacy cookie (old web), and then lands on `not_found`, or on the cancel page releasing nothing. The planner's "ships safely before or after" claim in 09 doesn't hold for this mix. | `.github/workflows/deploy.yml:88` (backend) before `:111` (web); prompt 10's `pickCheckout` spec | In `pickCheckout`, when a valid `ref` matches no entry, fall back to a **legacy (reference-null) entry** if there is one, never to another referenced entry. Add that test to 10. Correct 09's deploy-independence note. |
| FIX | Usability | `fragment_page.html` (06) includes the `#form` partial, whose `<form>` has `hx-post` / `hx-target="#grid"`. `dashboard/base.html` loads htmx, and the full page has no `#grid`, so in a JS-enabled browser that form's submit goes to a missing target and appears to do nothing. | `dashboard/templates/dashboard/schedule.html:119`; `dashboard/base.html` (htmx loaded, `responseHandling`) | Wrap the include in `<div hx-disable>` (htmx 2), so the form posts as a plain HTML form there. Assert the wrapper in 06's tests. |
| FIX | Prompt independence | In 03, "patch `Booking.save` so the `update_fields=[checkout_session_id…]` save raises" is ambiguous. `create_hold` (via `objects.create`) and `release()` also call `save`, so a blanket patch breaks the hold before the code under test runs. | `storefront/views.py:288-309`; `_release_failed_hold` → `holds.release` | Spell it out: wrap the original `Booking.save`, raise `DatabaseError` only when `"checkout_session_id" in (update_fields or ())`, and delegate otherwise. |
| FIX | Notes & constraints | 11 rewrites a `## Review constraints` Blocker rule ("URL parameters are never trusted" plus a `?ref=` clarification) inside a unit PR. Code-guardian would rightly flag an unapproved policy edit. | Plan: "Open questions"; prompt 11, CLAUDE.md bullet | Get the user's explicit approval now and record it in Decisions ("approved 2026-10-21"). Otherwise drop that bullet from 11 and keep only the Hidden-coupling update. |
| NOTE | Prompt independence | 04 adds `now=None` defaults to `queries.get_booking` / `schedule.booking_detail`, which read their **own** unpinned `timezone` (`queries.py:19`, `schedule.py:15`). The direct test calls (`test_bookings.py:308,600,720-733`, `test_schedule.py:461`) don't assert the viewer's `can_cancel`, so nothing breaks today. A new test that does would become a time bomb after 2026-11-02. | autouse `pinned_clock` only patches `views.timezone` (`test_bookings.py:110-113`, `test_schedule.py:161-164`) | In 04: any new direct call that asserts `can_cancel` passes `now=NOW`. |
| NOTE | Usability | 05 says the NUL tests fail "with a `ValueError`". psycopg 3.3.6 may raise `DataError` instead. | `uv run python -c "import psycopg; print(psycopg.__version__)"` → 3.3.6 | Reword it as "an exception (500)". |
| NOTE | Unit shape | CI runs on every `pull_request` (unit PRs into `develop` are covered), but `push` runs only on `main`. So the merged state of `develop` gets no CI run of its own. | `.github/workflows/ci.yml:3-6` | Acceptable: each PR's CI tests the merge ref. Consider adding `develop` to `push.branches` in a later hygiene unit (high-stakes workflow path, so not in this scope). |
| NOTE | Optimization | R8 lets invalid viewer creates through without charging the budget. Each costs one `Court` lookup (`ModelChoiceField`), the same as the unthrottled schedule GETs. | `dashboard/forms.py:62-66`; CBS-6 convention "Invalid requests don't count" | Accept. |
| NOTE | Model fit | 02 and 09 are opus for mechanical edits, which the rule requires (high-stakes `storefront/views.py`); effort is already medium. | workflow §6 | Accept. |

**Verified (no finding):**
- Django 6.1 `ModelChoiceField.to_python` rejects NUL (`django/forms/models.py:1587`), so POSTed form fields are safe and only the three lookups in 05 need guards.
- `settings_test.py` inherits `MIDDLEWARE` (`from .settings import *`), so 01's tests exercise the real order.
- The web `/api/*` routes already send no-store (`apps/web/next.config.ts:16`), so R1 is backend-only, correctly.
- The rename call sites are exactly those planned (`_normalise`: `core/http.py:38,41`; `_expire_session`: `confirm.py:231`; `_expire_checkout`: `dashboard/views.py:204`). No test patches them by name.
- The fixture reference `KC-7Q4M2X` matches the Crockford regex (`docs/api/fixtures/booking-created.json:2`; `actions.test.ts:45`).
- `settings.BASE_DIR` = `apps/backend` (`config/settings.py:15`), so 08's `site.ts` path is right.
- The runbook already shows `gcloud run jobs execute cb-nightly` (`docs/runbook.md:490`), which is where 08's line belongs.
- Every `can_cancel(` caller is in 04's file list.
- Every dashboard test that hits a fragment endpoint sends `headers=HX`; the only non-HX POST is `return=detail` (`test_bookings.py:766`), which stays unchanged.

**Bloat estimate:** planned ~31 files / ~900 LOC, about 60% of it tests. Minimal viable is about the same: every row traces to an R#, and no new dependency or config.
**Model cost:** as planned. 02 and 09 could be sonnet if the high-stakes rule allowed it; it doesn't.

**Applied 2026-10-21 (user approved all):**
- The BLOCK and the 5 FIXes are resolved in the plan (base `develop`; Release step; Decisions; Blast radius; Rollback; Log) and in prompts 03, 06, 09, 10 and 11.
- The NOTE tweaks went into 04 and 05.
- The constraint clarification is approved.
- The `CLAUDE.md` `Base branch: develop` change is left to the user's ledger commit.
- Status: audited.
