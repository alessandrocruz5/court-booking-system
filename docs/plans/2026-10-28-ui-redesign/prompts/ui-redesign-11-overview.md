---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 11
unit: CBS-20
status: done
model: sonnet
effort: medium
depends_on: [10]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/dashboard/templates/dashboard/overview.html
    - apps/backend/dashboard/queries.py
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/dashboard/tests/test_overview.py
  delete: []
---
# 11 · Overview restyle

## Task
Restyle the overview: stat cards, revenue-by-sport bars, gross/fees/net table, utilization heatmap.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Staff.dc.html` (startTab=overview).
- `queries.overview` already returns `_today`, `_revenue`, `_by_sport`, `_heatmap`, `_upcoming` and `_alerts`.
  - Add only presentation fields:
    - each `SportRevenue`'s bar width as a 0–100 integer relative to the top sport, rounded to 5 → class `.w-N`
    - each heatmap cell's bucket 0–9 → `.heat-N`
    - the week-over-week change if `_revenue` has both windows
  - **No new SQL** unless a stat in the spec has no source. In that case, leave it out and say so.
- `.heat-0`…`.heat-9` = `color-mix(in oklch, #16a34a {5..95}%, #f1f5f9)`, with white text from `.heat-6` up.
- The needs-refund alert stays (cause-neutral copy, 2026-10-21 R11).
- Tests: update the markup assertions and list them. Responses are CSP-safe.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
cd apps/backend && uv run pytest dashboard -q
```
