# Runbook

Kalaro Courts is a **fictional** sports complex, and this repo is a portfolio court-booking system for it. It holds
dummy data only and uses PayMongo in test mode, so no real payment is ever taken. Two apps live in this monorepo: the
Next.js storefront (`apps/web`, Cloud Run service `cb-web`) and the Django backend with the staff dashboard
(`apps/backend`, Cloud Run service `cb-backend` and job `cb-nightly`), both in `asia-southeast1`, on a Neon Postgres in
AWS `ap-southeast-1`, all on free tiers. Locally, both apps run from this repo against Postgres in Docker. Each later
change that adds a moving part adds its section here.

## Local development

Prerequisites:

- Node 24 (`.nvmrc`). Run `corepack enable` once, so `pnpm` resolves to the version pinned in the root
  `package.json` (`packageManager`).
- [uv](https://docs.astral.sh/uv/). It downloads the Python in `apps/backend/.python-version` (3.14) on first use.
- Docker, for the `db` service in `compose.yaml`: Postgres 17 on `localhost:54329` (54329 avoids a local Postgres on
  5432).

Once per clone, from the repo root:

```sh
corepack enable
pnpm install
docker compose up -d --wait db
```

Backend (`@cb/backend`, <http://localhost:8000>, health check at `/healthz`):

1. `cp apps/backend/.env.example apps/backend/.env`. The template documents every key, and `.env` is gitignored.
2. Generate a `DJANGO_SECRET_KEY` and paste it into `apps/backend/.env`:

   ```sh
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

3. `pnpm --filter @cb/backend dev`. It runs `runserver` on port 8000 through `uv run --env-file .env`, the only thing
   that reads the file.

Web (`@cb/web`, <http://localhost:3000>, health check at `/api/health`):

1. `cp apps/web/.env.example apps/web/.env.local`. The template documents every key, and `.env.local` is gitignored.
2. `pnpm --filter @cb/web dev`. It runs `next dev` on port 3000.

The full check chain, from the repo root, in this order. All of it must pass before a PR, and CI
(`.github/workflows/ci.yml`) runs the same steps against its own Postgres 17 on port 54329:

```sh
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
```

`pnpm test` needs the `db` service. `pnpm build` needs no environment variables: both apps read theirs per request.
`pnpm format` fixes TS/JSON (Prettier) and Python (ruff).

## Neon (once)

1. Create a Neon project in AWS `ap-southeast-1` (Singapore) with the default Postgres version, 17.
2. Keep two branches: `main` for production (rename the default branch if Neon named it otherwise) and `dev`,
   branched from it.
3. Copy the owner role's **direct** connection string, the one whose host has no `-pooler`, into `apps/backend/.env`
   as `MIGRATE_DATABASE_URL`. It is used only to run migrations from the laptop, and it never goes into GitHub or
   Cloud Run.

Free plan limits: 100 CU-hours of compute per month, and the compute scales to zero after 5 minutes without
connections. Any request that reaches the database wakes it and spends CU-hours, which is why there are no keep-warm
pings or uptime checks that touch the database, and why both health checks (`/healthz`, `/api/health`) answer without
querying it.
