---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 08
unit: U3
status: todo
model: opus
effort: high
depends_on: [07]
parallel_group: C
files:
  create:
    - apps/backend/dashboard/templates/dashboard/desk.html
    - apps/backend/dashboard/tests/test_desk.py
  modify:
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/urls.py
    - apps/backend/dashboard/static/dashboard/dashboard.css
  delete: []
---
# 08 · Front desk page and check-in action

## Task
Add the Front desk:
- `GET dashboard/desk/` (`?q=`)
- `GET dashboard/desk/suggest/` (htmx partial)
- `POST dashboard/desk/check-in/<reference>/`, named `check_in` (09 and 10 post to `dashboard:check_in`)

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Staff.dc.html` (startTab=desk).
- Views: `@staff_required` outermost, then `@require_GET` or `@require_POST`, as in `views.py`. Data only from `dashboard.desk` (06).
- `desk_view`: renders `desk.html` with the lookup form (a GET, works without JS), the result or not-found, the stats, arriving next and on court now.
  - Lookup input: mono, `autofocus`, `name="q"`.
  - Fills `dashboard_nav_badge` with the arriving count.
  - For the viewer, show "Try {ref1} or {ref2}" with two of today's demo references from `desk.arriving` (omit it when there are none).
- `suggest_view`: `hx-get` with `hx-trigger="input changed delay:250ms"` and `hx-target="#suggest"`. Returns the `desk.html#suggest` partial (Django 6 template partials, as `schedule.html` does).
  - Under 2 characters, or for a non-htmx request, return an empty partial (or redirect, following `_render_fragment`'s rule: never a bare fragment without htmx).
- **Response helpers** (`views.py:82-100`): `_render_fragment` and `_panel_message` are hard-wired to `dashboard/schedule.html` and retarget `#panel`, which the desk doesn't have.
  - Add a keyword-only `template: str = SCHEDULE` to `_render_fragment`. The default keeps every existing caller unchanged.
  - Desk refusals don't use `_panel_message`. They re-render `desk.html#desk` with a `message`, at status 403 or 429 (the htmx config already swaps both), with `HX-Retarget: #desk` and `HX-Reswap: outerHTML`.
- `check_in_view`:
  1. `schedule.get_booking(reference)` (with the NUL guard), else 404.
  2. `can_check_in` (403 `"You can't check in this booking."`, shown on the desk as above).
  3. `_viewer_write_allowed` (429 `DEMO_LIMIT`).
  4. `checkin.check_in(by=request.user, now=now)`.
  5. On htmx, re-render `desk.html#desk` with `?q=<reference>` state and an OOB toast `"{name} checked in · {court}"`. The name is masked for the viewer. Without htmx, 303 to `desk/?q=<reference>`.
  - `CheckInError` maps to a friendly message per code.
- The arriving-next row's "Check in" is a small form (`hx-post`) with `hx-target="#desk"`.
- **Landing**: keep `dashboard:overview` at `""` (the decision is in the plan). Add the desk at `desk/`.
- `dashboard.css`: `.desk-*` classes per the spec. No inline styles.
- `test_desk.py`:
  - anonymous → sign-in redirect
  - owner lookup shows the full contact; viewer lookup is masked
  - check-in happy path (toast, DB fields set)
  - the viewer can't check in a real online booking (403); the viewer can check in a demo booking
  - the viewer's suggest matches a demo booking's name but never a real one's
  - budget 429
  - wrong-day and ended → message, no change
  - `assert_csp_safe` on every response
  - a non-htmx suggest never returns a bare fragment

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
cd apps/backend && uv run pytest dashboard -q
```
