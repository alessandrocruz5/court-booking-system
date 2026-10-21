---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 01
unit: U1
status: todo
model: opus
effort: high
depends_on: []
parallel_group: A
files:
  create:
    - apps/backend/core/middleware.py
    - apps/backend/core/tests/test_no_store.py
  modify:
    - apps/backend/config/settings.py
  delete: []
---
# 01 · No-store middleware for `/api/` and `/webhooks/`

## Task
Make every backend response under `/api/` or `/webhooks/` carry `Cache-Control: no-store`. That includes the
responses no view produces: an unmatched-route 404, a 400 from `DisallowedHost`, a 413 from `RequestDataTooBig`,
and a 500. Do it with one small middleware placed **first** (outermost) in `MIDDLEWARE`.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329` (`docker compose up -d --wait db` from the repo root); test settings are
  `config/settings_test.py` (`ALLOWED_HOSTS = ["testserver", "localhost"]`).
- Review constraint (a merge Blocker): "`/api/v1/*` and `/webhooks/*` on the backend send `Cache-Control: no-store`."
  Today only the views do it: `storefront/auth.py:24-57` (`json_response`, `require_service_token`) and
  `payments/views.py:30-38` (`_no_store`). So `GET /api/v1/nope` gets Django's HTML 404 (`templates/404.html`) with no
  `Cache-Control`, and so does a `/webhooks/paymongo` request with a bad `Host`.
- `config/urls.py` mounts `webhooks/` (`payments.urls`) and `api/v1/` (`storefront.urls`).
- `config/settings.py` `MIDDLEWARE` starts with `SecurityMiddleware`, `WhiteNoiseMiddleware`, … Django wraps each
  middleware in `convert_exception_to_response`, so an outermost middleware sees the final response for exceptions
  raised in inner middleware (`CommonMiddleware`'s `request.get_host()` raises `DisallowedHost`) and for the URL
  resolver's 404.
- Write `apps/backend/core/middleware.py` in the style of `accounts/middleware.py`: a module docstring that says
  what it does and why it's outermost, and a plain `__init__(get_response)` / `__call__(request)` class:
  ```python
  _PREFIXES = ("/api/", "/webhooks/")

  class NoStoreMiddleware:
      def __init__(self, get_response): ...
      def __call__(self, request):
          response = self.get_response(request)
          if request.path.startswith(_PREFIXES):
              response["Cache-Control"] = "no-store"
          return response
  ```
  Insert `"core.middleware.NoStoreMiddleware"` as the first `MIDDLEWARE` entry, with a one-line comment on why it's
  first.
- **The build reads no env:** the settings must still import with an empty environment (a dotted string is fine).
- Keep the per-view no-store code; it's defence in depth. Don't remove or change it.
- Tests (`core/tests/test_no_store.py`, pytest-django, `@pytest.mark.django_db` where the DB is touched; copy the
  layout of `core/tests/`):
  - `GET /api/v1/does-not-exist` → 404, `Cache-Control: no-store`.
  - `GET /api/v1` (no trailing slash) → no-store.
  - `GET /webhooks/does-not-exist` → 404, no-store.
  - `POST /webhooks/paymongo` with `HTTP_HOST="evil.example"` → 400, no-store.
  - An existing API view still sends no-store, for example `GET /api/v1/catalog` without a token → 503 or 401.
  - A path outside the prefixes is untouched: `GET /` (the redirect to `/dashboard/`) has no `no-store` in
    `Cache-Control`.
  Confirm the 404, 400 and `/api/v1` tests fail without the middleware (comment it out once, run, then restore).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Remove the views' own no-store code, or change any other middleware's order.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && env -i PATH="$PATH" HOME="$HOME" DJANGO_SETTINGS_MODULE=config.settings uv run python -c "import django; django.setup()"
```
- `uv run pytest core/tests/test_no_store.py -q` passes, and its 404/400 cases fail with the middleware removed.
