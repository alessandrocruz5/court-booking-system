---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 20
unit: CBS-9
status: done
model: opus
effort: high
depends_on: [19]
parallel_group: T
files:
  create:
    - apps/backend/accounts/views.py
    - apps/backend/accounts/urls.py
    - apps/backend/accounts/templates/accounts/login.html
    - apps/backend/templates/base.html
    - apps/backend/templates/404.html
    - apps/backend/templates/500.html
    - apps/backend/core/static/core/base.css
    - apps/backend/accounts/tests/test_login.py
  modify:
    - apps/backend/config/urls.py
    - docs/runbook.md
  delete: []
---
# 20 · Staff sign-in, demo button and sign-out

## Task
Add the staff sign-in page at `/dashboard/login/` with three actions:
- the email/password form
- an **"Explore the owner demo"** button that signs in as the viewer **without any field posted**
- `POST /dashboard/logout/`

Both sign-in paths are rate-limited to 5 per minute per IP in the database. Add the shared `templates/base.html`, which
carries the test-mode banner.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`). Settings already have `LOGIN_URL = "/dashboard/login/"`,
  `LOGIN_REDIRECT_URL = "/dashboard/"`, the CSP middleware (nonce available as `{{ csp_nonce }}`), CSRF, and 12-hour sessions.
- Already there (prompt 19):
  - `accounts.roles.role_of(user)` and `Role`.
  - `accounts.decorators.staff_required`.
  - `accounts.middleware.DashboardLoginRedirectMiddleware`, which exempts `/dashboard/login/` and `/dashboard/demo/`.
  - `core.http.client_ip(request)`.
  - Accounts come from `manage.py seed_staff`, with `username == email`.
  - `core.ratelimit.hit(scope, ident, *, limit, window_seconds) -> bool`, which is DB-backed and keys on an HMAC of the IP.
- **The design being ported** (read only):
  - `/Users/alessandrocruz/Code/fun-run-website/apps/admin/app/login/page.tsx`: fixed error keys, nothing from the URL
    rendered, the demo section's copy, and redirecting away if already signed in.
  - `.../apps/admin/src/lib/auth/demo-login.ts`: the demo credentials live only on the server and the form posts no
    fields. It distinguishes `env_missing` from `credentials_rejected` in logs.
  - `.../apps/admin/src/lib/auth/server.ts`: `SignInOutcome` (`signed_in | invalid | rate_limited | unavailable`),
    logs carry reasons only, and session IP and user agent aren't kept.
- **`accounts/views.py`**:
  - `ERRORS` is a dict of fixed messages:
    - `invalid`: "That email and password don't match a staff account."
    - `rate_limited`: "Too many sign-in attempts. Wait a minute, then try again."
    - `unavailable`: "Sign-in isn't available right now. Try again in a moment."
    - `demo_unavailable`: "The demo isn't available right now. Try again later."
  - `def _sign_in(request, email, password) -> str`:
    1. `hit("staff_sign_in", client_ip(request), limit=5, window_seconds=60)`. If refused → `"rate_limited"`.
    2. `authenticate(request, username=email.strip().lower(), password=password)`. None, or `role_of(user)` is None →
       `"invalid"`.
    3. `login(request, user)`, which rotates the session key, then `"signed_in"`.
    4. A DB error → log the class name only → `"unavailable"`.
    5. Logs: `auth.sign_in_rejected reason=…` and `auth.sign_in_failed error=<class>`. **Never the email.**
  - `login_view`, GET and POST. GET: if already signed in with a role → redirect to `/dashboard/`. Read `?error=` but
    use it **only** as a key into `ERRORS`; nothing else from the URL is rendered. POST: run `_sign_in` with the form
    fields. Success → redirect to `/dashboard/` (ignore any `next` parameter, so there's no open redirect). Otherwise
    redirect to `/dashboard/login/?error=<outcome>`.
  - `demo_view`, POST only. Credentials come from env (`DEMO_VIEWER_EMAIL` and `DEMO_VIEWER_PASSWORD`, read per call).
    - Missing → log `auth.demo_unavailable reason=env_missing` → redirect to `?error=demo_unavailable`.
    - Otherwise run `_sign_in`. `invalid` → log `reason=credentials_rejected` (re-run `seed_staff`) → `demo_unavailable`.
    - Other outcomes redirect as above.
    - **The template's demo form contains only the CSRF token.**
  - `logout_view`, POST only: `logout(request)`, then redirect to login. GET → 405.
- **`accounts/urls.py`**: `login/`, `demo/` and `logout/`. In `config/urls.py`, add
  `path("dashboard/", include("accounts.urls"))` **before** any future dashboard include.
- **`templates/base.html`**: an HTML5 skeleton with these parts.
  - `{% load static %}`, a block `title`, a link to `{% static 'core/base.css' %}`, and an empty block `styles` for
    page-specific sheets. Only reference static files that exist: WhiteNoise's manifest storage raises on a missing
    one in production.
  - **`core/static/core/base.css`** holds the design tokens as CSS variables: `--ink` #0f172a, `--paper` #f8fafc,
    `--court` #16a34a, `--clay` #c2410c, `--line` #cbd5e1, `--error` #b91c1c. These are the same values as
    `apps/web/app/globals.css`; note that in a comment. It also covers a system font stack, the banner, forms,
    buttons (primary, outline, accent), alerts, and a focus-visible ring. It must be mobile-first.
  - A top banner `<aside aria-label="Test mode">● Fictional venue · Test mode, no real payments</aside>` on **every**
    page.
  - Blocks `header`, `content` and `scripts`.
  - **No inline scripts or styles.** CSP is `script-src 'self'` + nonce.
- **`templates/404.html`** extends `base.html`: the banner, "Page not found" and a link to `/dashboard/`.
  **`templates/500.html`** is self-contained, because Django renders it with no context: use only `{% load static %}`
  and the banner markup, and no blocks that need context. Both show the test-mode banner, since the rule covers every
  page of both apps.
- **`accounts/templates/accounts/login.html`**, extending `base.html`. It follows fun-run's login page.
  - The heading "KALARO COURTS · STAFF" / "Sign in".
  - The error alert (`role="alert"`).
  - A "New here?" section explaining the demo: "See the dashboard as a viewer with demo bookings. Customers' contact
    details are masked." It holds the **Explore the owner demo** button. Disable it with a note when the demo env is
    missing; the view passes `demo_available`.
  - The "Staff account" form with email (`autocomplete="username"`) and password (`autocomplete="current-password"`).
  - A link back to the storefront using `settings.SITE_URL`, passed in context.
- **`docs/runbook.md`**: append `## Staff dashboard`. Port fun-run's "Organizer dashboard" bullets (lines 294–399) to
  this stack:
  - Database access: link to `## Database roles and migrations` (CBS-4 wrote it). Don't repeat it.
  - Accounts: `STAFF_OWNER_*` and `DEMO_VIEWER_*` in `apps/backend/.env`, then
    `uv run --env-file .env python manage.py seed_staff` against each Neon branch. Re-running it rotates passwords and
    signs both accounts out.
  - How access works (the decorator vs the middleware), sign-in rate limiting, and the log events.
  - The production checks: `curl -sI $BACKEND_URL/dashboard/` → 302 to login; 6 bad sign-ins → the 6th shows the
    rate-limit message; demo button → header says VIEWER.
- **Tests** (`test_login.py`, using `seed_staff`-style fixtures):
  - GET login → 200 with the banner and a CSP header.
  - The right password → 302 to `/dashboard/`, with a session. The wrong password → `?error=invalid`. A user with no
    role → `invalid`.
  - The 6th attempt from the same IP within a minute → `rate_limited`, even with the right password. Pin the clock
    `core.ratelimit` reads, so the run can't straddle the 60-second window.
  - The demo POST with the env set → signed in as viewer. With the env missing → `demo_unavailable`. The demo form
    in the HTML has no inputs except `csrfmiddlewaretoken`.
  - `?error=<script>` renders no message and doesn't echo the value.
  - `?next=https://evil.example` is ignored.
  - Logout via GET → 405. Logout via POST → the session is gone.
  - Signed in, GET login → redirect to `/dashboard/`.
  - Log records (`caplog`) never contain the email.
  - `GET /no-such-page` → 404 with the banner. `django.views.defaults.server_error(request)` → 500 with the banner.
- Review constraints:
  - **Staff access**: no sign-up, accounts from the seed only, DB rate limit, demo credentials server-side only.
  - **Test mode**: the banner shows on every page.
  - **Personal data**: no emails in logs.
  - **CSP**: no inline scripts.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Render anything from the query string except as a key lookup.
- Put demo credentials in a template, hidden input or JS.
- Add the dashboard pages. That's prompt 21.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest accounts -q
```
