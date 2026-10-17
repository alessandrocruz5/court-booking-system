# Kalaro Courts: court booking system

An online court-booking system for **Kalaro Courts, a fictional sports complex**. It is a portfolio demo for court
owners: customers book and pay for a court online, and staff run the day from a dashboard. All data is dummy data and
PayMongo runs in **test mode only**, so no real payment is ever taken.

The venue has 2 basketball courts (full or half court; volleyball on a full court), 4 tennis courts and 12
badminton/pickleball courts. It is open daily 07:00–23:00 (Asia/Manila), and bookings open up to 7 days ahead.

## Architecture

```text
   Customer                      Staff                   PayMongo (test mode)
      |                            |                              |
      v                            |                              |
+--------------------+             |                              |
| cb-web             |             |                              |
| Next.js storefront |             |                              |
+--------------------+             |                              |
      | server-side only,          |                              |
      | bearer token               |                              | signed webhook
      v                            v                              v
+-------------------------------------------------------------------------+
| cb-backend (Django)                                                     |
|   /api/v1/*              /dashboard (HTMX)          /webhooks/paymongo  |
+-------------------------------------------------------------------------+
                                     |
                                     v
                    Neon Postgres (aws-ap-southeast-1)
```

- **`cb-web`** (`apps/web`) is the customer storefront. It holds no database credential and calls the backend's
  `/api/v1/*` from server code only.
- **`cb-backend`** (`apps/backend`) owns the schema, the booking rules, the PayMongo checkout, the webhook, the
  storefront API and the staff dashboard. A nightly Cloud Run job, `cb-nightly`, runs from the same image.
- Both services run on Google Cloud Run in `asia-southeast1`, on free tiers.

## Stack

- **Web:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, Zod, Vitest.
- **Backend:** Django 6.1 on Python 3.14 (managed by uv), HTMX, gunicorn, WhiteNoise, psycopg 3, pytest.
- **Data:** Postgres 17: Neon in production, Docker (`compose.yaml`) locally and in CI.
- **Payments:** PayMongo, test mode only.
- **Tooling:** pnpm workspaces and Turborepo, ESLint, Prettier, ruff, GitHub Actions (with a gitleaks scan), Dependabot.

## Quickstart

You need Node 24, uv and Docker. From the repo root:

```sh
corepack enable
pnpm install
docker compose up -d --wait db
```

Then follow [docs/runbook.md → Local development](docs/runbook.md#local-development) to create the env files and start
the backend (port 8000) and the storefront (port 3000), and for the full check chain CI runs.

## More

- [CLAUDE.md](CLAUDE.md): the project profile, with the commands, review constraints, high-stakes paths and hidden
  coupling.
- [docs/api/](docs/api/): the storefront API contract between `cb-web` and `cb-backend`.
- [docs/runbook.md](docs/runbook.md): operations.
- [docs/plans/](docs/plans/): feature plans.

## License

[MIT](LICENSE)
