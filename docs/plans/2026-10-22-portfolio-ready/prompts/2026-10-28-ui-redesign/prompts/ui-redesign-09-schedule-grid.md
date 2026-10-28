---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 09
unit: CBS-19
status: todo
model: sonnet
effort: high
depends_on: [08]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/dashboard/schedule.py
    - apps/backend/dashboard/templates/dashboard/schedule.html
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/tests/test_schedule.py
  delete: []
---
# 09 · Schedule: block grid, now marker, check-in in the panel

## Task
Render the schedule as the spec's CSS grid of **booking blocks**, add the now marker, and add Check in to the booking panel.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Staff.dc.html` (startTab=schedule).
- `schedule.build_grid` returns `Row`s per (court, space), with cells per hour.
  - Add to `Grid`:
    - `blocks`: one per booking per court. A full basketball booking is **one** block spanning both half rows.
      - Fields: `row`, `row_span` (1 or 2), `col` (hour − 5), `col_span` (hours), `state` (`online | checked_in | walk_in | pending | block | done`), name (masked), sub, reference.
    - `empty_cells`: row, col, court code, space, hour, addable.
    - `now_col` and `now_minute_class`, today only.
  - Keep the existing `Row` data the tests rely on, or update those tests and list them.
  - `done` = confirmed and ended. `checked_in` = `checked_in_at` set and not ended.
- Template (`#grid` partial): one `.sg` grid with `.r-N`, `.rs-2`, `.c-N` and `.cs-N` classes. No inline `style` (`assert_csp_safe`).
  - Generate those utility classes in `dashboard.css`: rows 2–26, cols 2–17, spans 1–3. Add `.now-m-0`…`.now-m-55` in 5-minute steps.
  - Empty cells keep today's `hx-get` to `dashboard:new`.
  - Blocks keep the `hx-get` to `dashboard:booking`.
  - Group rows and the legend follow the spec.
- Panel (`#panel`): the key/value list, Check in (`hx-post` to `dashboard:check_in` with `return=schedule`; 08's view returns `_grid_response` with the toast when `return=schedule`), and the existing Cancel.
  - In `views.py`, add `return` handling to `check_in_view`: `return=schedule` → `_grid_response` with the toast; `return=detail` → `_to_detail` (used by 10).
- Add form (`#form`): restyled per the spec. Same fields; viewer block notes stay a select.
- Tests:
  - A full basketball booking renders one block with `rs-2`.
  - A half booking renders `rs-1`.
  - A 3-hour booking renders `cs-3`.
  - The now marker appears only today.
  - Panel check-in works and refreshes the grid.
  - Every response is CSP-safe.

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
