---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 05
unit: CBS-3
status: done
model: opus
effort: high
depends_on: [04]
parallel_group: E
files:
  create:
    - apps/web/Dockerfile
    - apps/backend/Dockerfile
    - .dockerignore
    - apps/backend/.dockerignore
  modify:
    - .github/workflows/ci.yml
    - .github/dependabot.yml
    - CLAUDE.md
  delete: []
---
# 05 · Container images

## Task
Write production Dockerfiles for both apps, for Cloud Run. They must be multi-stage, run as non-root, build with
**no environment variables**, and listen on `$PORT` (8080). Add a CI `images` job that builds both and smoke-runs them,
add Docker to Dependabot, and add the two build commands to `CLAUDE.md`'s `## Commands`.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. There is no Dockerfile to copy: fun-run deployed on
  Vercel, and the only other Dockerfile on this machine runs as root, so it's not a pattern to follow.
- **Web image** (`apps/web/Dockerfile`, build context = **repo root**: `docker build -f apps/web/Dockerfile .`):
  - `apps/web` is Next.js 16 with `output: "standalone"` and `outputFileTracingRoot` set to the monorepo root, so the
    server is `.next/standalone/apps/web/server.js`. The pnpm workspace is pnpm 10.33 (root `packageManager`), Node 24
    (`.nvmrc`) and turbo 2.x (root devDependency).
  - Stages:
    1. `base`: `node:24-slim`, `corepack enable`, `NEXT_TELEMETRY_DISABLED=1`.
    2. `pruner`: `COPY . .`, then `turbo prune @cb/web --docker` (run the turbo version from the root `package.json`,
       e.g. `pnpm dlx turbo@<that version> prune …`).
    3. `builder`: copy `out/json/` and `out/pnpm-lock.yaml`, run `pnpm install --frozen-lockfile` with a BuildKit
       cache mount for the pnpm store, copy `out/full/`, then `pnpm turbo run build --filter=@cb/web`. **No ENV or
       ARG secrets.**
    4. `runner`: `node:24-slim`, `NODE_ENV=production`, `HOSTNAME=0.0.0.0`, `PORT=8080`. Copy the standalone dir,
       `apps/web/.next/static` → `apps/web/.next/static`, and `apps/web/public` → `apps/web/public`, all with
       `--chown=node:node`. Then `USER node`, `EXPOSE 8080`, `CMD ["node", "apps/web/server.js"]`.
  - The first line is `# syntax=docker/dockerfile:1`.
- **Backend image** (`apps/backend/Dockerfile`, build context = **`apps/backend`**: `docker build apps/backend`):
  - It's a Django 6.1 / Python 3.14 project managed by uv 0.13.0 (`pyproject.toml`, `uv.lock`, `.python-version`). The
    gunicorn config is `config/gunicorn.conf.py`: it binds `0.0.0.0:$PORT` and validates the runtime env in
    `on_starting`. Settings import with an empty env.
  - Stages:
    1. `builder`: `python:3.14-slim`, `COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/`, and
       `UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv`, and `WORKDIR /app`.
       `uv sync --locked --no-dev --no-install-project`, using bind mounts for `pyproject.toml`/`uv.lock` and a cache mount.
       Then `COPY . .`, then `DJANGO_SETTINGS_MODULE=config.settings /app/.venv/bin/python manage.py collectstatic
       --noinput`, **with no other env**.
    2. `runtime`: `python:3.14-slim`, `WORKDIR /app`, a system user and group `app`, `PATH=/app/.venv/bin:$PATH`,
       `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `PORT=8080`. `COPY --from=builder --chown=app:app /app /app`,
       then `USER app`, `EXPOSE 8080`, `CMD ["gunicorn", "config.wsgi", "-c", "config/gunicorn.conf.py"]`.
  - The same image later runs the Cloud Run Job (`python manage.py nightly`), so don't hard-code an `ENTRYPOINT`.
- **`.dockerignore`** (repo root, used by the web build): exclude `**/node_modules`, `**/.next`, `**/.turbo`, `.git`,
  `**/.env*` (keeping `!**/.env.example`), `coverage`, `docs/plans`, `apps/backend/.venv`, `apps/backend/staticfiles` and
  `**/__pycache__`. **Keep `apps/backend/package.json`**, because turbo prune reads every workspace manifest.
  **`apps/backend/.dockerignore`**: `.venv`, `staticfiles`, `**/__pycache__`, `.pytest_cache`, `.ruff_cache`, `.env*`
  (keeping `!.env.example`), `**/tests`.
- **CI `images` job** in `.github/workflows/ci.yml`, alongside `verify` and `secrets`, with `permissions: contents: read`:
  - `actions/checkout@v7`, then `docker/setup-buildx-action` and `docker/build-push-action` at their current majors
    (look them up with `gh api repos/docker/<name>/releases/latest --jq .tag_name`). Build both images with
    `push: false`, `load: true`, tags `cb-web:ci` and `cb-backend:ci`, and `cache-from/to: type=gha,scope=<web|backend>`
    (`mode=max` on the write).
  - Smoke web: `docker run -d --name web -p 8080:8080 -e SITE_URL=http://localhost:8080 cb-web:ci`. Poll
    `curl -fsS localhost:8080/api/health` for up to 30 s. Assert `curl -sI localhost:8080/` has a
    `content-security-policy` header, and that `docker exec web id -u` is not `0`.
  - Smoke backend: generate a throwaway secret in the step (`python3 -c "import secrets;print(secrets.token_urlsafe(50))"`).
    Run `-p 8081:8080` with `DJANGO_SECRET_KEY` set to it,
    `DATABASE_URL=postgres://ci:ci@127.0.0.1:5432/ci` (never connected), `ALLOWED_HOSTS=localhost`,
    `CSRF_TRUSTED_ORIGINS=http://localhost:8081`, `SITE_URL=http://localhost:8080` and `INTERNAL_API_TOKEN` (a random
    40-character value generated the same way). Poll `curl -fsS localhost:8081/healthz`. Assert the container user isn't
    root. Then assert that starting it **without** `DJANGO_SECRET_KEY` exits non-zero (fail-fast env validation).
  - Mark the generated values `# gitleaks:allow` only if the scan flags them. They're generated, never committed.
- **`.github/dependabot.yml`**: add `docker` entries for `/apps/web` and `/apps/backend`, weekly.
- **`CLAUDE.md`**: append these two lines to the end of the `## Commands` code block, after `pnpm build`:
  `docker build -f apps/web/Dockerfile -t cb-web:local .` and `docker build -t cb-backend:local apps/backend`.
- Review constraints: **the build reads no env**; secrets stay on the server; **free tier** (small images help both
  cold starts and the 0.5 GB Artifact Registry allowance).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Push images, add registry logins or add deploy steps. Prompt 06 does that.
- Bake any env value or secret into an image. Use `ENV` only for `NODE_ENV`, `HOSTNAME`, `PORT`, `PATH` and `PYTHON*`/`UV_*`.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend
docker run --rm cb-web:local id -u | grep -vx 0
docker run --rm cb-backend:local id -u | grep -vx 0
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep -E 'cb-(web|backend):local'   # report sizes
pnpm format:check && pnpm lint
```
- Run the two smoke runs above locally with the same env as CI: both health routes answer 200, and the backend
  without `DJANGO_SECRET_KEY` exits non-zero with a message naming the key, not a value.
