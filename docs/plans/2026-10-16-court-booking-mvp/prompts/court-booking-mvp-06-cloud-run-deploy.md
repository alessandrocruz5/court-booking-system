---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 06
unit: CBS-3
status: done
model: opus
effort: high
depends_on: [05]
parallel_group: F
files:
  create:
    - .github/workflows/deploy.yml
  modify:
    - docs/runbook.md
  delete: []
---
# 06 · Cloud Run deploy pipeline

## Task
Add a GitHub Actions **Deploy** workflow. After CI passes on `main` (or on manual dispatch), it builds both images,
pushes them to Artifact Registry through Workload Identity Federation (no JSON keys), and deploys the Cloud Run services
`cb-backend` and `cb-web` and the Cloud Run Job `cb-nightly`, with free-tier settings. Document the one-time GCP owner
setup in the runbook.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. CI is `.github/workflows/ci.yml` (`name: CI`, jobs
  `verify`, `images` and `secrets`). The images are `apps/web/Dockerfile` (context `.`) and `apps/backend/Dockerfile`
  (context `apps/backend`), both on port 8080.
- **Workflow `.github/workflows/deploy.yml`**:
  - `name: Deploy`. `on: workflow_run: {workflows: [CI], types: [completed], branches: [main]}` plus `workflow_dispatch`.
  - `concurrency: {group: deploy, cancel-in-progress: false}`.
  - One job, `deploy`, with
    `if: vars.GCP_PROJECT_ID != '' && (github.event_name == 'workflow_dispatch' || (github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'))`.
    It's skipped until the owner sets the variables (the same pattern fun-run used for `TURBO_TEAM`).
  - `permissions: {contents: read, id-token: write}`. `runs-on: ubuntu-latest`.
  - `env`: `REGION: asia-southeast1`, `REGISTRY: asia-southeast1-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/cb`, and
    `SHA: ${{ github.event.workflow_run.head_sha || github.sha }}`. Deploy exactly the commit CI tested:
    check out `ref: ${{ env.SHA }}`.
  - Steps, using current majors looked up with `gh api repos/<owner>/<repo>/releases/latest --jq .tag_name`:
    `actions/checkout`, `google-github-actions/auth` (`workload_identity_provider: ${{ vars.GCP_WIF_PROVIDER }}`,
    `service_account: ${{ vars.GCP_DEPLOY_SA }}`), `google-github-actions/setup-gcloud`, then
    `gcloud auth configure-docker asia-southeast1-docker.pkg.dev --quiet`, `docker/setup-buildx-action`, and
    `docker/build-push-action` twice (push `$REGISTRY/web:$SHA` and `$REGISTRY/backend:$SHA`, with GHA cache scopes
    `web` and `backend`).
  - Deploy with plain `gcloud` commands (easier to review than the deploy action):
    - `gcloud run deploy cb-backend --image $REGISTRY/backend:$SHA --region $REGION --allow-unauthenticated
      --min-instances 0 --max-instances 1 --cpu 1 --memory 512Mi --concurrency 40 --cpu-boost --timeout 60
      --service-account cb-runtime@${{ vars.GCP_PROJECT_ID }}.iam.gserviceaccount.com
      --set-env-vars ALLOWED_HOSTS=<host of vars.BACKEND_URL>,CSRF_TRUSTED_ORIGINS=${{ vars.BACKEND_URL }},SITE_URL=${{ vars.WEB_URL }},DEMO_VIEWER_EMAIL=${{ vars.DEMO_VIEWER_EMAIL }}
      --set-secrets DJANGO_SECRET_KEY=cb-django-secret-key:latest,DATABASE_URL=cb-database-url:latest,INTERNAL_API_TOKEN=cb-internal-api-token:latest,PAYMONGO_SECRET_KEY=cb-paymongo-secret-key:latest,PAYMONGO_WEBHOOK_SECRET=cb-paymongo-webhook-secret:latest,DEMO_VIEWER_PASSWORD=cb-demo-viewer-password:latest`.
      Derive the host in bash: `BACKEND_HOST="${BACKEND_URL#https://}"`.
    - `gcloud run deploy cb-web --image $REGISTRY/web:$SHA`, with the same region, scaling, CPU, memory, boost and service-account
      flags, `--concurrency 80`,
      `--set-env-vars API_URL=${{ vars.BACKEND_URL }},SITE_URL=${{ vars.WEB_URL }},DASHBOARD_URL=${{ vars.BACKEND_URL }}/dashboard/`
      and `--set-secrets INTERNAL_API_TOKEN=cb-internal-api-token:latest`.
    - `gcloud run jobs deploy cb-nightly --image $REGISTRY/backend:$SHA --region $REGION --command python
      --args manage.py,nightly --tasks 1 --max-retries 1 --task-timeout 600 --cpu 1 --memory 512Mi
      --service-account cb-runtime@… --set-env-vars ALLOW_DEMO_SEED=1,SITE_URL=${{ vars.WEB_URL }},ALLOWED_HOSTS=localhost
      --set-secrets DJANGO_SECRET_KEY=cb-django-secret-key:latest,DATABASE_URL=cb-database-url:latest`.
      The `nightly` command arrives in a later unit. Until then the job exists but nothing schedules it.
    - Smoke check: `curl -fsS --retry 5 --retry-delay 5 ${{ vars.BACKEND_URL }}/healthz` and the same for
      `${{ vars.WEB_URL }}/api/health`.
  - Comment the free-tier choices inline: min 0 (scale to zero), max 1 (a cost cap: one instance per service is plenty for a demo,
    and it halves the worst case under a traffic flood), request-based billing (the default
    CPU throttling: don't pass `--no-cpu-throttling`), and CPU boost for cold starts.
- **`docs/runbook.md`**: append `## Cloud Run (once)`, `## Deploy` and `## Roll back`. Write them as numbered,
  copy-pasteable `gcloud` steps. The owner runs them. Never put real values in the file.
  1. A GCP project linked to a billing account. Create a **$1 budget** with alerts at 50/90/100%. The free tier needs
     billing, and this guards against surprises. Expect a few cents a month at most: outbound data transfer outside
     North America (pages to visitors, queries to Neon on AWS) isn't in the free tier. A budget alert only emails; it
     doesn't stop spending.
  2. Enable `run`, `artifactregistry`, `secretmanager`, `iamcredentials`, `sts` and `cloudscheduler`.
  3. An Artifact Registry Docker repo `cb` in `asia-southeast1`, with a **cleanup policy** that keeps the 2 most recent
     versions per image and deletes untagged images after 1 day. The free allowance is 0.5 GB.
  4. Service accounts. `cb-deployer` gets `roles/run.admin`, `roles/artifactregistry.writer` on repo `cb`, and
     `roles/iam.serviceAccountUser` on `cb-runtime`. `cb-runtime` gets `roles/secretmanager.secretAccessor` on the six
     secrets **only**, not project-wide.
  5. Workload Identity Federation: a pool `github` and an OIDC provider `github`
     (`https://token.actions.githubusercontent.com`). Restrict the attribute condition to
     `assertion.repository == '<owner>/court-booking-system' && assertion.ref == 'refs/heads/main'`, then let that
     principal impersonate `cb-deployer`.
  6. **Six Secret Manager secrets**, which is exactly the free allowance of 6 active versions: `cb-django-secret-key`,
     `cb-database-url`, `cb-internal-api-token`, `cb-paymongo-secret-key`, `cb-paymongo-webhook-secret` and
     `cb-demo-viewer-password`. Give the generation commands
     (`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`). Until the units that need them ship, placeholders
     are fine:
     - `cb-database-url`: `postgres://pending:pending@127.0.0.1:5432/pending` (CBS-4's `## Database roles and
       migrations` replaces it)
     - `cb-paymongo-secret-key`: `sk_test_pending`
     - `cb-paymongo-webhook-secret`: `pending` (CBS-5's `## PayMongo (test mode)` replaces both PayMongo values)
     After a rotation, **disable or destroy the old version** to stay at 6 active.
  7. URLs are deterministic: `https://cb-backend-<PROJECT_NUMBER>.asia-southeast1.run.app` and
     `https://cb-web-<PROJECT_NUMBER>.asia-southeast1.run.app`. Confirm after the first deploy with
     `gcloud run services describe <svc> --region asia-southeast1 --format='value(status.url)'`. Set these GitHub
     repo **variables** (not secrets): `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER` (the full provider resource name),
     `GCP_DEPLOY_SA`, `BACKEND_URL`, `WEB_URL` and `DEMO_VIEWER_EMAIL`.
  8. First deploy: Actions → Deploy → Run workflow. Later deploys run automatically after CI passes on `main`.
  9. Free-tier guardrails: min 0 and max 1; **no uptime checks or keep-warm pings** (Neon's 100 CU-hours a month would
     run out); Cloud Scheduler gives 3 free jobs per billing account, and the plan uses 1.
  10. Roll back: `gcloud run services update-traffic <svc> --region asia-southeast1 --to-revisions <rev>=100`, or
      revert the PR so the workflow redeploys. Migrations are additive, so the code can roll back alone.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Store a JSON service-account key, a secret value or a real project ID anywhere in the repo.
- Run migrations from CI or Cloud Run. Migrations run from a laptop, as the owner.
- Add `--no-cpu-throttling`, `--min-instances` above 0, or uptime checks.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
uvx --from pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"
command -v actionlint >/dev/null && actionlint .github/workflows/deploy.yml || echo "actionlint not installed: skipped"
grep -c 'min-instances 0' .github/workflows/deploy.yml   # 2 (both services)
grep -c 'max-instances 1' .github/workflows/deploy.yml   # 2 (both services)
! grep -nE 'credentials_json|sk_test_[A-Za-z0-9]{8,}' .github/workflows/deploy.yml
pnpm format:check && pnpm lint
```
- Reading the workflow: with `vars.GCP_PROJECT_ID` unset, the job is skipped, not failed.
