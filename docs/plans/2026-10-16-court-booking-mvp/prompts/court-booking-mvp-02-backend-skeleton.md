---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 02
unit: CBS-2
status: todo
model: opus
effort: high
depends_on: [01]
parallel_group: B
files:
  create:
    - apps/backend/package.json
    - apps/backend/pyproject.toml
    - apps/backend/uv.lock
    - apps/backend/.python-version
    - apps/backend/manage.py
    - apps/backend/.env.example
    - apps/backend/conftest.py
    - apps/backend/config/__init__.py
    - apps/backend/config/env.py
    - apps/backend/config/settings.py
    - apps/backend/config/settings_test.py
    - apps/backend/config/urls.py
    - apps/backend/config/wsgi.py
    - apps/backend/config/gunicorn.conf.py
    - apps/backend/core/__init__.py
    - apps/backend/core/apps.py
    - apps/backend/core/views.py
    - apps/backend/core/logging.py
    - apps/backend/core/tests/__init__.py
    - apps/backend/core/tests/test_health.py
    - apps/backend/core/tests/test_env.py
    - apps/backend/core/tests/test_logging.py
    - compose.yaml
  modify:
    - package.json
    - turbo.json
    - pnpm-lock.yaml
  delete: []
---
# 02 · Django backend skeleton

## Task
Create `apps/backend`, a Django 6.1 project managed by uv and wired into Turborepo through a `package.json` script
shim. Give it production-grade settings for Cloud Run and Neon, a no-DB `/healthz` route, fail-fast runtime env
validation, pytest against a local Postgres 17 from `compose.yaml`, and ruff.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Prompt 01 created the pnpm/Turbo root (`@cb/*` scope).
- This Django service later owns the database (Neon Postgres), the booking rules, PayMongo, the webhook, a JSON
  API for the Next.js storefront, and an HTMX staff dashboard. Today it only boots and answers `/healthz`.
- Toolchain: `uv` 0.13 is installed and manages Python. Pin **Python 3.14** in `.python-version` and set
  `requires-python = ">=3.14,<3.15"`; uv downloads the interpreter itself. Add dependencies with `uv add`:
  - runtime: `django>=6.1,<6.2`, `psycopg[binary]>=3.3`, `dj-database-url>=3` (parses Neon URLs), `gunicorn>=26`,
    `whitenoise>=6.12`
  - dev group (`uv add --dev`): `pytest`, `pytest-django>=4.14`, `ruff`
  - In `pyproject.toml`, set `[tool.uv] package = false` (an app, not a library) and `[project] name = "cb-backend"`.
- **The build reads no env.** The Docker build (a later prompt) runs `collectstatic` with **no** environment variables.
  `config/settings.py` must therefore import with an empty environment: no exceptions at import, and no DB connection.
  - `config/env.py` holds small helpers: `env_str(name, default="")`, `env_bool(name, default=False)` (accepts
    `1/true/yes/on`), `env_list(name)` (comma-separated, trimmed, with empty items dropped) and
    `validate_runtime_env(environ=os.environ)`. That last one raises `ImproperlyConfigured` listing **every** missing
    or blank key by name, never a value.
  - `REQUIRED_RUNTIME_ENV = ("DJANGO_SECRET_KEY", "DATABASE_URL", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
    "SITE_URL", "INTERNAL_API_TOKEN")`. This list covers every key the whole plan requires at runtime, so later
    prompts never need to change CI or deploy. PayMongo and demo keys are validated per use, not here.
    `DJANGO_SECRET_KEY` must also be at least 50 characters, and `INTERNAL_API_TOKEN` at least 32.
  - `config/gunicorn.conf.py` calls `validate_runtime_env()` in `on_starting(server)`.
- **`config/settings.py`**, matching each line below:
  - `SECRET_KEY = env_str("DJANGO_SECRET_KEY")`. It's empty at build time, and Django refuses an empty key on first use.
  - `DEBUG = env_bool("DJANGO_DEBUG")`. `ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")`, plus `localhost` and `127.0.0.1` when
    DEBUG. `CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")`. `SITE_URL = env_str("SITE_URL").rstrip("/")`.
    `INTERNAL_API_TOKEN = env_str("INTERNAL_API_TOKEN")`.
  - `INSTALLED_APPS`: `django.contrib.auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`, `core`.
    **No `django.contrib.admin`**: the plan's staff dashboard replaces it, and it's a review constraint.
  - `MIDDLEWARE`, in this order: `SecurityMiddleware`, `whitenoise.middleware.WhiteNoiseMiddleware`, `SessionMiddleware`,
    `CommonMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware`, `MessageMiddleware`,
    `XFrameOptionsMiddleware`, then Django 6's CSP middleware (`django.middleware.csp.ContentSecurityPolicyMiddleware`).
    **Verify the exact module and setting names in the installed Django** (`.venv/lib/python3.14/site-packages/django/
    middleware/csp.py`, `django/utils/csp.py`) before writing them.
  - CSP via `SECURE_CSP`: `default-src 'self'`; `script-src 'self'` + nonce; `style-src 'self' 'unsafe-inline'`;
    `img-src 'self' data:`; `font-src 'self'`; `connect-src 'self'`; `form-action 'self'`; `frame-ancestors 'none'`;
    `base-uri 'self'`; `object-src 'none'`. Add the CSP context processor so templates get `csp_nonce`.
  - `DATABASES = {"default": dj_database_url.parse(env_str("DATABASE_URL") or "postgres://build:build@127.0.0.1:5432/build", conn_max_age=0)}`.
    Then set `DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True`, because Neon's pooler is PgBouncer in transaction mode.
    Do **not** set `server_side_binding`: client-side binding avoids prepared statements.
  - `TIME_ZONE = "Asia/Manila"`, `USE_TZ = True`, `LANGUAGE_CODE = "en-us"`, `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`.
  - Static: `STATIC_URL = "static/"`, `STATIC_ROOT = BASE_DIR / "staticfiles"`, and `STORAGES` with WhiteNoise's
    `CompressedManifestStaticFilesStorage` for `staticfiles`.
  - `TEMPLATES`: `DIRS = [BASE_DIR / "templates"]`, `APP_DIRS = True`, and the context processors `request`, `auth`,
    `messages` and csp.
  - Proxy and security: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`. When not DEBUG, also set
    `SECURE_SSL_REDIRECT = True`, `SECURE_REDIRECT_EXEMPT = [r"^healthz$"]`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
    and `SECURE_HSTS_SECONDS = 31536000` (no includeSubDomains or preload). Always: `SESSION_COOKIE_AGE = 60 * 60 * 12`,
    `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_HTTPONLY = True`,
    `SECURE_REFERRER_POLICY = "same-origin"`, `X_FRAME_OPTIONS = "DENY"`, `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"`.
  - `AUTH_PASSWORD_VALIDATORS`: minimum length 12, common password, numeric.
  - `LOGGING`: one stdout console handler with format `%(levelname)s %(name)s %(message)s`. The root logger is at
    WARNING, the `cb` logger namespace at INFO, and `django.request` at ERROR. Never log request bodies, query
    strings or personal data.
  - `core/logging.py`: `class RedactingFormatter(logging.Formatter)`. Its `formatException(ei)` keeps the stack frames
    (`traceback.format_tb`) but replaces the exception's text with its class name, plus `sqlstate=<code>` when the
    exception or its `__cause__` has a psycopg `sqlstate`. Why: psycopg's message is libpq's full text, so a CHECK
    violation carries `DETAIL: Failing row contains (…name, email, mobile…)`, and `django.request` logs every 500
    with its traceback. The console handler uses `{"()": "core.logging.RedactingFormatter", "format": …}`. The
    module must import with no env.
- `config/settings_test.py`: `from .settings import *  # noqa`. Set a fixed 64-character test `SECRET_KEY`, `DEBUG = False`,
  `ALLOWED_HOSTS = ["testserver", "localhost"]`, `SECURE_SSL_REDIRECT = False`, and
  `DATABASES["default"] = dj_database_url.parse(os.environ.get("TEST_DATABASE_URL", "postgres://postgres:postgres@localhost:54329/cb"), conn_max_age=0)`
  (keep `DISABLE_SERVER_SIDE_CURSORS`). Also set `STORAGES["staticfiles"]` to plain `StaticFilesStorage`,
  `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]`, `INTERNAL_API_TOKEN = "t" * 40` and
  `SITE_URL = "http://localhost:3000"`.
- `config/gunicorn.conf.py`: `bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"`, `workers` from `WEB_CONCURRENCY`
  (default 2), `worker_class = "gthread"`, `threads = 4`, `timeout = 30`, `graceful_timeout = 10`, `accesslog = "-"` with
  `access_log_format = '%(m)s %(U)s %(s)s %(b)s %(L)s'` (path without the query string, no IP and no user agent:
  this keeps personal data out of logs), `errorlog = "-"`, `forwarded_allow_ips = "*"` (Cloud Run's front end is the
  only peer), and the `on_starting` hook.
- `config/urls.py`: `path("healthz", core.views.healthz)`. `core/views.py` `healthz` handles GET only and returns
  `JsonResponse({"status": "ok"})` with `Cache-Control: no-store`. It **never touches the DB**, so uptime probes can't
  keep Neon awake.
- `compose.yaml` at the repo root holds one service, `db`, running `postgres:17-alpine` with
  `POSTGRES_USER/PASSWORD/DB = postgres/postgres/cb`, ports `54329:5432` (the Homebrew Postgres on 5432 must not
  clash), and a `pg_isready -U postgres -d cb` healthcheck with a 2 s interval and 30 retries, so
  `docker compose up -d --wait db` works.
- `apps/backend/package.json` (Turbo shim), named `@cb/backend`, `private`, version `0.0.0`, with these scripts:
  - `"dev": "uv run --env-file .env python manage.py runserver 8000"`
  - `"format": "uv run ruff format ."`
  - `"lint": "uv run --locked ruff check . && uv run --locked ruff format --check ."`
  - `"test": "uv run --locked python manage.py makemigrations --check --dry-run --settings=config.settings_test && uv run --locked pytest"`
  - Leave out `typecheck` and `build`, so Turbo skips them for this package.
- Root `package.json`: change `format` to `prettier --write "**/*.{ts,tsx,js,mjs,cjs,json}" && pnpm --filter @cb/backend format`.
  Leave `format:check` as is; ruff's format check runs in `lint`.
- `turbo.json`: Turbo 2 runs tasks in strict env mode. Run `pnpm test` and `pnpm lint` from the root. If uv
  fails because it lacks `HOME`, a cache directory or `TEST_DATABASE_URL`, add exactly the names it needs to
  `globalPassThroughEnv` (likely `HOME`, `UV_CACHE_DIR`, `XDG_CACHE_HOME`, `TEST_DATABASE_URL`). Add nothing speculative.
- pyproject: `[tool.ruff]` with `line-length = 100`, `target-version = "py314"` and `extend-exclude = ["staticfiles"]`.
  `[tool.ruff.lint] select = ["E", "F", "W", "I", "B", "UP", "DJ", "S", "SIM"]`, with per-file ignores
  `"**/tests/**" = ["S101", "S105", "S106", "S603", "S607"]`, `"conftest.py" = ["S101"]` and
  `"config/settings_test.py" = ["S105"]` (its fixed test key trips S105). Under `[tool.pytest.ini_options]`, set
  `DJANGO_SETTINGS_MODULE = "config.settings_test"`, `python_files = ["test_*.py"]` and `addopts = "-q --strict-markers"`.
- `.env.example` (backend). Comment each key (what it is, server only, where it's used) in the style of
  `/Users/alessandrocruz/Code/fun-run-website/apps/web/.env.example`. Keys: `DJANGO_SECRET_KEY=`, `DJANGO_DEBUG=1`,
  `DATABASE_URL=postgres://postgres:postgres@localhost:54329/cb`, `ALLOWED_HOSTS=localhost,127.0.0.1`,
  `CSRF_TRUSTED_ORIGINS=http://localhost:8000`, `SITE_URL=http://localhost:3000`, `INTERNAL_API_TOKEN=`, and
  `MIGRATE_DATABASE_URL=` (the Neon owner's **direct**, non-`-pooler` connection string, used only for `migrate` from
  a laptop; never in GitHub or Cloud Run). Add a note that
  `uv run --env-file .env` loads it and that `.env` is gitignored.
- Tests:
  - `core/tests/test_health.py`: 200, `{"status": "ok"}` and `no-store`, with zero DB queries (`django_assert_num_queries(0)`).
    POST gets a 405.
  - `core/tests/test_env.py`: `validate_runtime_env({})` names all 6 keys. A short secret key or token fails. The
    message never contains a value (pass a sentinel value and assert it's absent). `env_list` trims and drops blanks.
  - Prove "import without env": a test runs `python -c "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()"`
    in a subprocess with an **empty** environment (except PATH), and it succeeds.
  - `core/tests/test_logging.py`: format a record whose `exc_info` is an exception with the text
    `Failing row contains (Juan, juan@example.com)` and a `sqlstate` of `23514`. The output has the class name,
    `sqlstate=23514` and a stack line, and contains neither the email nor `Failing row`.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies beyond those listed (no django-environ, no python-dotenv, no DRF).
- Install `django.contrib.admin`, add models or migrations of your own, or read env at import in any way that
  can raise.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm install --frozen-lockfile
pnpm lint                 # includes ruff check + ruff format --check for @cb/backend
pnpm test                 # includes makemigrations --check and pytest for @cb/backend
cd apps/backend && env -i PATH="$PATH" HOME="$HOME" uv run python manage.py collectstatic --noinput --dry-run   # no env needed
uv run python manage.py check --deploy --settings=config.settings_test
```
- `pnpm --filter @cb/backend dev` (after copying `.env.example` to `.env` and filling `DJANGO_SECRET_KEY`) serves
  `http://localhost:8000/healthz` → `{"status":"ok"}`.
