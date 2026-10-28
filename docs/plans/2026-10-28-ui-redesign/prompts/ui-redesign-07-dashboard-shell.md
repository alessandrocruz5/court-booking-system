---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 07
unit: CBS-20
status: done
model: sonnet
effort: medium
depends_on: [06]
parallel_group: C
files:
  create:
    - apps/backend/core/static/core/fonts/Archivo-Variable.woff2
    - apps/backend/core/static/core/fonts/JetBrainsMono-Bold.woff2
    - apps/backend/core/static/core/fonts/OFL.txt
  modify:
    - apps/backend/core/static/core/base.css
    - apps/backend/dashboard/static/dashboard/dashboard.css
    - apps/backend/dashboard/templates/dashboard/base.html
    - apps/backend/templates/base.html
    - apps/backend/dashboard/tests/test_bookings.py
    - apps/backend/dashboard/tests/test_schedule.py
  delete: []
---
# 07 · Dashboard shell: sidebar, tokens, fonts

## Task
Replace the dashboard's header nav with the spec's sidebar shell, and bring the spec's tokens, type and controls into `dashboard.css`.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Staff.dc.html` (sidebar, main header, toast).
- Self-host the fonts. The CSP is likely `font-src 'self'`: check `config/settings.py` and **don't edit it** (high-stakes). Download the woff2 files from the upstream OFL releases and include `OFL.txt`. Add `@font-face` in `core/base.css`.
- `dashboard/base.html`:
  - The header block becomes `<aside class="dash-side">`, with brand, nav, role badge and the Sign out POST form.
    - Nav items in order: Front desk (`dashboard:desk`, added in 08; until then guard with `{% url 'dashboard:desk' as desk_url %}{% if desk_url %}`), Schedule, Bookings, Overview.
    - Keep `aria-current="page"`.
    - The badge count goes in an empty template block, `dashboard_nav_badge`, which 08 fills on the desk page only. There's no context processor, so the other pages show no badge.
  - The `hx-headers` CSRF attribute moves to the aside and stays on the content wrapper.
  - Keep the htmx meta config as it is.
  - Add `dashboard_eyebrow` (the Manila date/time line) and `dashboard_heading` (the H1, default "Dashboard") blocks in the main header. **Don't reuse `dashboard_title`**: it is already defined inside `{% block title %}` (`dashboard/base.html:15`), and Django rejects a block name defined twice. Each page template sets both `dashboard_title` and `dashboard_heading`.
- `templates/base.html`: only what the new layout needs (a body class hook). The banner stays on every page, with the dot.
- `dashboard.css`:
  - Keep every class that the schedule, bookings and overview templates use today until 09–11 replace them.
  - Add the tokens as CSS custom properties, plus `.btn`, `.btn-primary`, `.btn-dark`, `.btn-outline`, `.btn-ghost`, `.seg`, `.pill pill-{status_key}`, `.card`, `.stat`, `.toast` (bottom-centre, auto-hide via `@keyframes`, no JS), and `.tag tag-{sport}` (the sport colours).
- Layout: `.dash` is a flex row, `.dash-side` 232px and sticky, `.dash-main` has padding `28px 32px 48px`. Under 900px the sidebar becomes a top bar (horizontal nav).
- Existing tests that assert header markup: `test_bookings.py:187` and `:498`, `test_schedule.py:248`. Update them to the new markup and list them in the report.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.
- Edit `config/settings.py`.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
cd apps/backend && uv run pytest dashboard accounts -q && cd ../..
docker build -t cb-backend:local apps/backend
```
- `collectstatic` (in the image build) runs with no env.
