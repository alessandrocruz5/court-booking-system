---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 19
unit: CBS-9
status: done
model: opus
effort: xhigh
depends_on: [18]
parallel_group: S
files:
  create:
    - apps/backend/accounts/__init__.py
    - apps/backend/accounts/apps.py
    - apps/backend/accounts/roles.py
    - apps/backend/accounts/decorators.py
    - apps/backend/accounts/middleware.py
    - apps/backend/accounts/management/__init__.py
    - apps/backend/accounts/management/commands/__init__.py
    - apps/backend/accounts/management/commands/seed_staff.py
    - apps/backend/accounts/tests/__init__.py
    - apps/backend/accounts/tests/test_access.py
    - apps/backend/accounts/tests/test_seed_staff.py
    - apps/backend/core/http.py
  modify:
    - apps/backend/config/settings.py
    - apps/backend/.env.example
  delete: []
---
# 19 · Staff roles, seeded accounts and access checks

## Task
Port fun-run's organizer-dashboard access model to Django's built-in auth:
- two roles, `owner` and `viewer`, as Django Groups
- accounts created **only** by `manage.py seed_staff` (no sign-up anywhere)
- a `@staff_required` decorator that is the real access check
- a redirect-only middleware fast path
- a trusted client-IP helper

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests on Postgres at `localhost:54329`). `django.contrib.auth` and `sessions` are installed; **`django.contrib.admin`
  isn't, and must stay out**. `SESSION_COOKIE_AGE` is 12 h. Password validators require a minimum length of 12.
- **The design being ported** (read only, for intent):
  - `/Users/alessandrocruz/Code/fun-run-website/apps/admin/src/lib/auth/roles.ts`: the `owner` and `viewer` roles and
    `canSeePersonalData`.
  - `.../apps/admin/src/lib/auth/session.ts`: `requireSession()` is the real check, and the proxy only redirects.
  - `.../packages/db/src/seed-organizers.ts`: upserts by email from env, resets passwords, signs both accounts out
    everywhere, and is the only way accounts exist.
  - `.../docs/runbook.md` lines 294–399: the organizer dashboard section.
- **`core/http.py`**: `def client_ip(request) -> str`. It takes the **rightmost** entry of `HTTP_X_FORWARDED_FOR`, the
  address Cloud Run's front end appended; anything to its left is client-supplied. Fall back to `REMOTE_ADDR`, then
  `"0.0.0.0"`. Validate with `ipaddress`. Document the assumption, since the runbook verifies it in production.
- **`accounts/roles.py`**:
  - `class Role(StrEnum)` with `OWNER = "owner"` and `VIEWER = "viewer"`.
  - `def role_of(user) -> Role | None`. It returns None for anonymous or inactive users and for users in no role
    group. If a user is somehow in both groups, the owner wins.
  - `def can_see_personal_data(role) -> bool` is true for the owner only.
  - `def can_create_staff_booking(role) -> bool` is true for both roles. The demo is meant to be hands-on.
  - `def can_cancel(role, booking) -> bool`. The owner can cancel any `pending` or `confirmed` booking. The viewer only
    when `booking.is_demo or booking.source != "online"`, so the public demo can never cancel a real visitor's
    online booking.
- **`accounts/decorators.py`**: `def staff_required(view)`.
  - An anonymous user, or one with no role → redirect to `settings.LOGIN_URL` (`/dashboard/login/`).
  - For an HTMX request (header `HX-Request: true`), respond 200 with an empty body and the header
    `HX-Redirect: /dashboard/login/` instead.
  - Otherwise set `request.staff_role` and call the view.
  - Also add a `never_cache` effect: `Cache-Control: no-store, private` on every staff response.
- **`accounts/middleware.py`**, `DashboardLoginRedirectMiddleware`: if the path starts with `/dashboard/` and isn't
  `/dashboard/login/` or `/dashboard/demo/`, and the user isn't authenticated, redirect to login. **It only
  redirects.** Comment that `@staff_required` on each view is the real check, because middleware ordering and HTMX
  partials make the middleware alone insufficient. Place it after `AuthenticationMiddleware`.
- **`seed_staff` command**:
  - Read `STAFF_OWNER_EMAIL`, `STAFF_OWNER_PASSWORD`, `DEMO_VIEWER_EMAIL` and `DEMO_VIEWER_PASSWORD` from env.
    A missing variable → exit 2 naming the variable. A password shorter than 16 characters → exit 2.
  - `get_or_create` the groups `owner` and `viewer`.
  - Upsert each user with `username=email.lower()` and `email=email.lower()`, `is_staff=False`, `is_superuser=False`,
    `is_active=True`. `set_password`, then set the groups to exactly their one role.
  - **Delete every session belonging to those two users.** Scan `Session` objects and decode them, or keep it simple
    by deleting the sessions whose `get_decoded().get("_auth_user_id")` matches. Re-running therefore rotates passwords
    and signs both out everywhere.
  - Print the role names, **never the emails or passwords**.
- `apps/backend/.env.example`: add `STAFF_OWNER_EMAIL=`, `STAFF_OWNER_PASSWORD=`, `DEMO_VIEWER_EMAIL=` and
  `DEMO_VIEWER_PASSWORD=` (16+ characters), with empty values. Comment that `seed_staff` reads all four from the
  laptop, and the demo button on Cloud Run also reads `DEMO_VIEWER_*`.
- **Settings**:
  - Add `"accounts"` to `INSTALLED_APPS`, and the middleware after `AuthenticationMiddleware`.
  - `LOGIN_URL = "/dashboard/login/"`, `LOGIN_REDIRECT_URL = "/dashboard/"`.
  - `AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]`. The username is the email.
  - `SESSION_SAVE_EVERY_REQUEST = False`.
- **Tests**:
  - `test_access.py`. Use dummy views decorated with `staff_required`, set up via `urls` override with
    `@pytest.mark.urls` or a test urlconf module defined in the test file.
    - Anonymous → 302 to login.
    - HTMX anonymous → 200 with `HX-Redirect`.
    - A user with no group → 302.
    - Viewer and owner → 200 with `request.staff_role` set.
    - An inactive user → 302.
    - The response has `no-store`.
    - The middleware: `/dashboard/anything` anonymous → 302, and `/dashboard/login/` passes.
    - The `can_cancel` matrix: owner × online, the viewer × online-real refused, the viewer × online-demo allowed,
      the viewer × walk-in allowed, and any role × cancelled refused.
    - `client_ip`: `"1.1.1.1, 2.2.2.2"` → `"2.2.2.2"`, garbage → `REMOTE_ADDR`.
  - `test_seed_staff.py`:
    - Creates both accounts with the right groups and no superuser or staff flags.
    - Re-running with a new password changes it and deletes their existing sessions (create one by logging in with
      the test client first).
    - A missing env var → `SystemExit` code 2, and the output contains no password.
    - A short password is refused.
- Review constraints:
  - **Staff access**: `@staff_required` everywhere, the middleware only redirects, no sign-up, no admin, accounts from
    the seed only.
  - **Personal data**: no emails or passwords in output or logs.
  - **Database roles**: no new tables, since Groups and Sessions are Django's own.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add sign-up, password-reset or password-change views, or install `django.contrib.admin`.
- Add login views or templates. That's prompt 20.
- Grant `is_staff` or `is_superuser` to anyone.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest accounts core -q
! grep -rn "django.contrib.admin" config/
```
