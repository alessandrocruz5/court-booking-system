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

## Cloud Run (once)

The owner runs these steps once, from a laptop with `gcloud` signed in as a project owner. Replace each `<…>` with
your own value; none of them belong in the repo. Every later step reuses these shell variables:

```sh
PROJECT_ID=<your-project-id>
BILLING_ACCOUNT=<your-billing-account-id>
GITHUB_REPO=<owner>/court-booking-system
gcloud config set project "$PROJECT_ID"
```

1. A GCP project linked to a billing account, with a **$1 budget** that alerts at 50, 90 and 100%. The free tier needs
   billing, and the budget guards against surprises. Expect a few cents a month at most: outbound data transfer
   outside North America (pages to visitors, queries to Neon on AWS) isn't in the free tier. A budget alert only
   emails; it doesn't stop spending. The budget command needs the Billing Budget API, or create the same budget in the
   console under Billing → Budgets & alerts.

   ```sh
   gcloud billing projects link "$PROJECT_ID" --billing-account "$BILLING_ACCOUNT"
   gcloud services enable billingbudgets.googleapis.com
   gcloud billing budgets create --billing-account "$BILLING_ACCOUNT" --display-name cb-budget \
     --budget-amount 1USD --filter-projects "projects/$PROJECT_ID" \
     --threshold-rule percent=0.5 --threshold-rule percent=0.9 --threshold-rule percent=1.0
   ```

2. Enable the APIs (`iam` is needed to create the service accounts and the identity pool):

   ```sh
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
     iamcredentials.googleapis.com sts.googleapis.com cloudscheduler.googleapis.com iam.googleapis.com
   ```

3. An Artifact Registry Docker repo `cb` in `asia-southeast1`, with a cleanup policy that keeps the 2 most recent
   versions of each image and deletes everything else after 1 day, untagged images included. An image tagged `keep-…`
   is never deleted: `## Roll back` uses that to protect the image a pinned revision runs. The free allowance is
   0.5 GB.

   ```sh
   gcloud artifacts repositories create cb --repository-format docker --location asia-southeast1
   cat > /tmp/cb-cleanup.json <<'JSON'
   [
     {"name": "keep-2-most-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
     {"name": "keep-pinned", "action": {"type": "Keep"}, "condition": {"tagState": "TAGGED", "tagPrefixes": ["keep-"]}},
     {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"tagState": "ANY", "olderThan": "1d"}}
   ]
   JSON
   gcloud artifacts repositories set-cleanup-policies cb --location asia-southeast1 \
     --policy /tmp/cb-cleanup.json --no-dry-run
   ```

4. Two service accounts. `cb-deployer` is what GitHub Actions acts as: it deploys Cloud Run, pushes to repo `cb` only,
   and may attach `cb-runtime` to the services. `cb-runtime` is what the services and the job run as; it gets its
   secret access in step 6, per secret.

   ```sh
   gcloud iam service-accounts create cb-deployer --display-name "GitHub Actions deployer"
   gcloud iam service-accounts create cb-runtime --display-name "Cloud Run runtime"
   DEPLOYER="cb-deployer@$PROJECT_ID.iam.gserviceaccount.com"
   RUNTIME="cb-runtime@$PROJECT_ID.iam.gserviceaccount.com"
   gcloud projects add-iam-policy-binding "$PROJECT_ID" \
     --member "serviceAccount:$DEPLOYER" --role roles/run.admin --condition None
   gcloud artifacts repositories add-iam-policy-binding cb --location asia-southeast1 \
     --member "serviceAccount:$DEPLOYER" --role roles/artifactregistry.writer
   gcloud iam service-accounts add-iam-policy-binding "$RUNTIME" \
     --member "serviceAccount:$DEPLOYER" --role roles/iam.serviceAccountUser
   ```

5. Workload Identity Federation, so GitHub Actions signs in with no JSON key: a pool `github` and an OIDC provider
   `github` that accepts tokens only from the Deploy workflow on this repo's `main` branch, started by a CI run or by
   hand. Any other workflow, even one on `main`, is refused. The repo and its owner are matched by numeric id, not
   by name, so a repo recreated under the same name after a rename or deletion doesn't match. Only that repo may
   impersonate `cb-deployer`.

   ```sh
   PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
   GITHUB_REPO="$(gh api "repos/$GITHUB_REPO" --jq .full_name)"  # exact case, as workflow_ref spells it
   REPO_ID="$(gh api "repos/$GITHUB_REPO" --jq .id)"
   OWNER_ID="$(gh api "repos/$GITHUB_REPO" --jq .owner.id)"
   gcloud iam workload-identity-pools create github --location global --display-name "GitHub Actions"
   gcloud iam workload-identity-pools providers create-oidc github \
     --location global --workload-identity-pool github \
     --issuer-uri https://token.actions.githubusercontent.com \
     --attribute-mapping 'google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref' \
     --attribute-condition "assertion.repository_id == '$REPO_ID' && assertion.repository_owner_id == '$OWNER_ID' \
   && assertion.ref == 'refs/heads/main' \
   && assertion.workflow_ref == '$GITHUB_REPO/.github/workflows/deploy.yml@refs/heads/main' \
   && assertion.event_name in ['workflow_run', 'workflow_dispatch']"
   gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --role roles/iam.workloadIdentityUser \
     --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository_id/$REPO_ID"
   ```

6. **Six Secret Manager secrets**, exactly the free allowance of 6 active versions, each stored in `asia-southeast1`
   only, and readable by `cb-runtime` only. The values are piped straight into `gcloud`, so they never land on screen
   or in a file. Until the units that need them ship, placeholders are fine: `cb-database-url` is replaced by
   `## Database roles and migrations` (CBS-4), and both PayMongo values by `## PayMongo (test mode)` (CBS-5).

   ```sh
   new_secret() { gcloud secrets create "$1" --replication-policy user-managed --locations asia-southeast1 --data-file -; }
   python3 -c "import secrets; print(secrets.token_urlsafe(50), end='')" | new_secret cb-django-secret-key
   python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" | new_secret cb-internal-api-token
   python3 -c "import secrets; print(secrets.token_urlsafe(24), end='')" | new_secret cb-demo-viewer-password
   printf '%s' 'postgres://pending:pending@127.0.0.1:5432/pending' | new_secret cb-database-url
   printf '%s' 'sk_test_pending' | new_secret cb-paymongo-secret-key
   printf '%s' 'pending' | new_secret cb-paymongo-webhook-secret
   for s in cb-django-secret-key cb-database-url cb-internal-api-token cb-paymongo-secret-key \
     cb-paymongo-webhook-secret cb-demo-viewer-password; do
     gcloud secrets add-iam-policy-binding "$s" \
       --member "serviceAccount:$RUNTIME" --role roles/secretmanager.secretAccessor
   done
   ```

   To change a value later, add a version (`… | gcloud secrets versions add <secret> --data-file -`), redeploy, then
   **destroy the old version** (`gcloud secrets versions destroy <version> --secret <secret>`) to stay at 6 active.
   A disabled version still counts as active.

7. GitHub repo **variables** (Settings → Secrets and variables → Actions → Variables; not secrets: none of them is
   secret). The service URLs are deterministic, so they can be set before the first deploy. No trailing slashes.

   ```sh
   gh variable set GCP_PROJECT_ID --body "$PROJECT_ID"
   gh variable set GCP_WIF_PROVIDER --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github"
   gh variable set GCP_DEPLOY_SA --body "$DEPLOYER"
   gh variable set BACKEND_URL --body "https://cb-backend-$PROJECT_NUMBER.asia-southeast1.run.app"
   gh variable set WEB_URL --body "https://cb-web-$PROJECT_NUMBER.asia-southeast1.run.app"
   gh variable set DEMO_VIEWER_EMAIL --body "<viewer>@example.com"
   ```

   After the first deploy, confirm both URLs match what Cloud Run reports, and fix the variables if not:

   ```sh
   gcloud run services describe cb-backend --region asia-southeast1 --format='value(status.url)'
   gcloud run services describe cb-web --region asia-southeast1 --format='value(status.url)'
   ```

8. First deploy: Actions → Deploy → Run workflow, on `main`. Later deploys run automatically after CI passes on
   `main`.
9. Free-tier guardrails. Both services run with min 0 and max 1 instances and request-based billing. **No uptime
   checks or keep-warm pings**: they would keep waking Neon and run out its 100 CU-hours a month. Cloud Scheduler
   gives 3 free jobs per billing account, and this project uses 1 (the nightly job, once its unit ships).

## Deploy

The **Deploy** workflow (`.github/workflows/deploy.yml`) runs after every green CI run of a push to `main`. It
builds both images at the commit CI tested, pushes them to Artifact Registry as `web:<sha>` and `backend:<sha>`,
deploys `cb-backend` and `cb-web`, updates the job `cb-nightly`, and smoke-checks `/healthz` and `/api/health`. It
is skipped while the `GCP_PROJECT_ID` variable is unset.

1. To redeploy by hand (after a secret change, say): Actions → Deploy → Run workflow, on `main`. The identity pool
   accepts only `main`, so a run from another branch fails at sign-in. A manual run deploys the head of `main` and
   stops before signing in unless CI passed on that exact commit; if CI is still running, wait for it.
2. The workflow never runs migrations. A change that needs one: apply the migration from the laptop first, then
   merge. Migrations are additive (expand/contract), so the running code keeps working against the new schema.
3. Deploys queue one at a time; a running deploy is never cancelled.

## Roll back

Artifact Registry keeps only the 2 most recent images per service, so the previous revision is the one you can
roll back to.

1. Find the last good revision, tag its image `keep-rollback` so the cleanup policy can't delete it while it serves
   (with min 0 instances, every cold start pulls the image again), and send all traffic to it:

   ```sh
   gcloud run revisions list --service cb-backend --region asia-southeast1
   IMAGE="$(gcloud run revisions describe <revision> --region asia-southeast1 \
     --format='value(spec.containers[0].image)')"
   gcloud artifacts docker tags add "$IMAGE" "${IMAGE%:*}:keep-rollback"
   gcloud run services update-traffic cb-backend --region asia-southeast1 --to-revisions <revision>=100
   ```

   The same for `cb-web`. Migrations are additive, so the code can roll back alone.
2. Or revert the PR on `main`: CI passes, and the workflow redeploys the previous code.
3. While traffic is pinned to a revision, new deploys create revisions that get no traffic. Once the fix is
   deployed, send traffic back to the latest revision and drop the protective tag:

   ```sh
   gcloud run services update-traffic cb-backend --region asia-southeast1 --to-latest
   gcloud artifacts docker tags delete "asia-southeast1-docker.pkg.dev/$PROJECT_ID/cb/backend:keep-rollback"
   ```

   The same for `cb-web` (its tag is `…/cb/web:keep-rollback`), if you rolled it back too.

## Secret exposure

If a secret reaches GitHub (the CI `secrets` job, gitleaks, fails) or leaks anywhere else, rotate it at once.
Removing the commit from history is not enough on its own: clones, forks and caches may already hold it.

1. Revoke it at the source first, where there is one. For `cb-paymongo-secret-key`, roll the key in the PayMongo
   dashboard (test mode). For `cb-database-url`, reset the role's password in Neon and build the new URL from it.
2. Add a new Secret Manager version for the affected `cb-*` secret, piped in so it never lands on screen. For the
   generated ones, use the same command as in `## Cloud Run (once)`, step 6:

   ```sh
   python3 -c "import secrets; print(secrets.token_urlsafe(50), end='')" \
     | gcloud secrets versions add cb-django-secret-key --data-file -
   ```

3. Redeploy: Actions → Deploy → Run workflow, on `main`. Cloud Run picks up `:latest` in the new revisions.
4. Disable the old version, then destroy it once the new revisions serve (a disabled version still counts toward the
   6 active):

   ```sh
   gcloud secrets versions list cb-django-secret-key
   gcloud secrets versions disable <old-version> --secret cb-django-secret-key
   gcloud secrets versions destroy <old-version> --secret cb-django-secret-key
   ```

Rotating `cb-django-secret-key` signs everyone out. `cb-internal-api-token` is shared by both services, and the
workflow redeploys both.

## Database roles and migrations

The backend never runs as the Neon owner. Migration `core.0002_app_role` creates the group role `cb_app` (NOLOGIN,
DML only: no DDL, and `django_migrations` is read-only to it), and Cloud Run connects as `cb_app_login`, a member of
it. Do this once per Neon branch, `dev` first and then `main`, when CBS-4 merges and before CBS-6 or CBS-7 deploy.

1. Run the migrations from the laptop only, as the owner, over the **direct** endpoint (the host without `-pooler`).
   Export `MIGRATE_DATABASE_URL` in the shell for the branch being migrated: for `main`, the string from
   `## Neon (once)`, step 3; for `dev`, the same owner string with the `dev` branch selected in Neon → Connect (keep
   it in the shell only). Then, from `apps/backend`:

   ```sh
   DATABASE_URL="$MIGRATE_DATABASE_URL" uv run python manage.py migrate
   ```

   Every later migration runs the same way, as the owner. `ALTER DEFAULT PRIVILEGES` grants `cb_app` access only to
   tables the owner creates, so a table created by any other role is invisible to the app. Migrations are additive
   (expand/contract), and an applied migration is never edited.

2. Create the runtime login once per branch, in `PSQL_HISTORY=/dev/null psql "$MIGRATE_DATABASE_URL"` (as the owner;
   the history override keeps the password out of `~/.psql_history`). **Never create it in the Neon Console**, which
   makes console roles members of `neon_superuser`. Generate the password with `openssl rand -hex 32` (hex needs no
   escaping in a URL):

   ```sql
   CREATE ROLE cb_app_login LOGIN PASSWORD '<password>' IN ROLE cb_app;
   ```

   No migration creates a login role or holds a password.

3. For `main`, put `cb_app_login`'s **pooled** connection string into the `cb-database-url` secret, replacing the
   placeholder from `## Cloud Run (once)`, step 6: the host with `-pooler`, and `?sslmode=require`. Pipe it in so it
   never lands on screen (the `read -s` prompt doesn't echo):

   ```sh
   read -rs DB_URL   # cb_app_login's pooled URL: host <endpoint>-pooler.<region>.aws.neon.tech, db neondb, ?sslmode=require
   printf '%s' "$DB_URL" | gcloud secrets versions add cb-database-url --data-file -
   unset DB_URL
   ```

   Redeploy (Actions → Deploy → Run workflow, on `main`), then disable the old version and destroy it once the new
   revisions serve, to stay at 6 active versions (a disabled version still counts):

   ```sh
   gcloud secrets versions list cb-database-url
   gcloud secrets versions disable <old-version> --secret cb-database-url
   gcloud secrets versions destroy <old-version> --secret cb-database-url
   ```

4. Check the runtime role, on each branch. Paste `cb_app_login`'s connection string at the silent prompt. The first
   query must print `18` (the grants work), and the second must fail with `permission denied for schema public`
   (no DDL):

   ```sh
   read -rs DATABASE_URL
   psql "$DATABASE_URL" -c "SELECT count(*) FROM bookings_court"
   psql "$DATABASE_URL" -c "CREATE TABLE x(id int)"
   unset DATABASE_URL
   ```

The reverse of `0002_app_role` revokes `cb_app`'s grants but keeps the role: roles are cluster-wide, and other
databases on the cluster may use it.
