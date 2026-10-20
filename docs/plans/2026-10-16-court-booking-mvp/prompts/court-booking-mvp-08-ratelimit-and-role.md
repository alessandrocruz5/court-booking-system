---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 08
unit: CBS-4
status: done
model: opus
effort: high
depends_on: [07]
parallel_group: H
files:
  create:
    - apps/backend/core/models.py
    - apps/backend/core/ratelimit.py
    - apps/backend/core/migrations/__init__.py
    - apps/backend/core/migrations/0001_ratelimit.py
    - apps/backend/core/migrations/0002_app_role.py
    - apps/backend/core/tests/test_ratelimit.py
    - apps/backend/core/tests/test_grants.py
  modify:
    - docs/runbook.md
  delete: []
---
# 08 · Rate limiter and least-privilege app role

## Task
Add (1) a database-backed, multi-instance-safe fixed-window rate limiter in `core`, and (2) a migration that creates
the least-privilege group role `cb_app` (DML only, no DDL, can't write `django_migrations`). The backend's runtime
login role (`cb_app_login`) is a member of `cb_app`.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests use `config.settings_test` against Postgres 17 at `localhost:54329`, user `postgres`, a superuser). The apps
  installed so far are `django.contrib.{auth,contenttypes,sessions,messages,staticfiles}`, `core` and `bookings`
  (migrations `0001_initial` and `0002_courts`). `core` has no models yet.
- Production DB: Neon. The **owner** role (`neondb_owner`) runs migrations from a laptop (`MIGRATE_DATABASE_URL`). Cloud
  Run connects as `cb_app_login`, which the owner creates by hand after this migration (this prompt's runbook
  section covers it): `CREATE ROLE cb_app_login LOGIN PASSWORD '…' IN ROLE cb_app;`.
- Pattern reference, **read only**: `/Users/alessandrocruz/Code/fun-run-website/packages/db/drizzle/0001_app_role.sql`.
  It uses an idempotent `DO $$ … IF NOT EXISTS … CREATE ROLE … NOLOGIN` and `REVOKE CREATE ON SCHEMA public FROM PUBLIC`.
- **Rate limiter**:
  - `core/models.py`: `class RateLimit(models.Model)` with `key = CharField(max_length=120, primary_key=True)`,
    `window_start = DateTimeField()` and `count = PositiveIntegerField()`. `db_table = "core_ratelimit"`.
  - `core/ratelimit.py`: `def hit(scope: str, ident: str, *, limit: int, window_seconds: int, now: datetime | None = None) -> bool`.
    It returns True if the request is allowed.
    - The key is `f"{scope}:{digest}"`, where `digest = hmac.new(settings.SECRET_KEY.encode(), ident.encode(), sha256).hexdigest()[:40]`.
      **Never store the raw IP or email** (RA 10173).
    - `window_start` = now floored to a multiple of `window_seconds` (epoch based, UTC).
    - One atomic statement through `connection.cursor()`:
      `INSERT INTO core_ratelimit (key, window_start, count) VALUES (%s, %s, 1) ON CONFLICT (key) DO UPDATE SET
      count = CASE WHEN core_ratelimit.window_start = EXCLUDED.window_start THEN core_ratelimit.count + 1 ELSE 1 END,
      window_start = EXCLUDED.window_start RETURNING count`. Allowed if `count <= limit`.
    - `def prune(*, older_than: timedelta = timedelta(days=1), now=None) -> int` deletes stale rows. The nightly job uses it.
    - On a DB error, raise. The caller decides. Never log `ident`.
  - `0001_ratelimit` comes from `makemigrations core`.
- **`0002_app_role`**: `RunSQL` with a reverse. Make it depend on `("core", "0001_ratelimit")`, `("bookings", "0002_courts")`,
  and the latest migrations of `auth`, `contenttypes` and `sessions`, so every table that exists today gets the
  grants. Forward SQL:
  ```sql
  DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cb_app') THEN CREATE ROLE cb_app NOLOGIN; END IF;
  END $$;
  REVOKE CREATE ON SCHEMA public FROM PUBLIC;
  GRANT USAGE ON SCHEMA public TO cb_app;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cb_app;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cb_app;
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE django_migrations FROM cb_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cb_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cb_app;
  ```
  - Put a comment at the top explaining the following. Default privileges apply to tables later created **by the
    role that ran this migration**, so every migration must run as the owner. `cb_app_login` is created by hand, never
    in the Neon Console. The role is cluster-wide, so the `IF NOT EXISTS` guard makes test databases and re-runs safe.
  - Reverse: `ALTER DEFAULT PRIVILEGES … REVOKE …` for both, and `REVOKE ALL ON ALL TABLES/SEQUENCES IN SCHEMA public FROM cb_app`.
    Don't drop the role, because other databases on the cluster may use it.
- **Tests**:
  - `test_ratelimit.py` (`django_db`):
    - The 1st through `limit`th calls are allowed and the next is refused.
    - A new window resets the count.
    - Different scopes and idents are independent.
    - The stored key contains neither the raw ident nor the IP (assert the ident string isn't in any key).
    - `prune` deletes old rows.
    - Concurrency: 10 threads hit the same key with `limit=5` under `django_db(transaction=True, serialized_rollback=True)`, and exactly 5 are
      allowed. Close each thread's connection.
  - `test_grants.py` (`django_db(transaction=True, serialized_rollback=True)`). Use `connection.cursor()` with `SET ROLE cb_app` in a try/finally
    that runs `RESET ROLE`:
    - `SELECT`, `INSERT` and `DELETE` on `bookings_court` and `core_ratelimit` succeed. Insert a throwaway rate-limit
      row and delete it.
    - `CREATE TABLE t_forbidden (id int)` raises `ProgrammingError` / insufficient privilege.
    - `INSERT INTO django_migrations (app, name, applied) VALUES ('x','y',now())` raises.
    - `SELECT` on `django_migrations` succeeds.
    - Wrap each expected failure in its own savepoint (`transaction.atomic()`).
  - Every transactional test uses `serialized_rollback=True`. Django empties every table after each one and
    pytest-django runs them after the rest, so without it the 18 seeded courts are gone for the next test.
- **`docs/runbook.md`**: append `## Database roles and migrations`. The owner follows it when this unit merges, and CBS-6
  and CBS-7 need it before they deploy:
  - Migrations run from the laptop only, as the Neon owner, over the **direct** (non-`-pooler`) endpoint:
    `DATABASE_URL="$MIGRATE_DATABASE_URL" uv run python manage.py migrate`, once per Neon branch (`dev`, then `main`).
    Every later migration also runs as the owner, because `ALTER DEFAULT PRIVILEGES` covers only the owner's tables.
  - Then create the runtime login once per branch:
    `CREATE ROLE cb_app_login LOGIN PASSWORD '<openssl rand -base64 32>' IN ROLE cb_app;`. Never create it in the
    Neon Console, which gives console roles `neon_superuser`.
  - Put the **pooled** connection string for `cb_app_login` (`-pooler` host, `sslmode=require`) into the
    `cb-database-url` secret, replacing the placeholder, and disable the old version so 6 stay active.
  - Check it: `psql "$DATABASE_URL" -c "CREATE TABLE x(id int)"` must fail with permission denied.
- Review constraints: **database roles** (DML only for the runtime; migrations as owner; expand/contract; never
  edit an applied migration) and **personal data** (no raw IPs or emails stored).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Create a LOGIN role or put any password in a migration.
- Use Django's cache framework for rate limiting (it isn't atomic across instances).
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
grep -n '## Database roles and migrations' docs/runbook.md
cd apps/backend && uv run pytest core -q
```
