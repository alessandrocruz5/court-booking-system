---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 08
unit: CBS-15
status: done
model: haiku
effort: low
depends_on: []
parallel_group: D
files:
  create: []
  modify:
    - apps/backend/bookings/tests/test_nightly.py
    - turbo.json
    - docs/runbook.md
  delete: []
---
# 08 · Drift tests, prune boundary, nightly runbook note

## Task
1. Add three tests to `apps/backend/bookings/tests/test_nightly.py`:
   - Every rate-limit window ≤ the nightly prune age.
   - The backend `RETENTION_DAYS` equals the web's.
   - The 10-minute prune boundary.
2. Add `apps/web/src/content/site.ts` to Turbo's test inputs.
3. Add one runbook line about manual nightly runs.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Backend: `apps/backend` (Python 3.14, uv, pytest-django). Tests run
  on Postgres at `localhost:54329`.
- Constants:
  - `bookings/management/commands/nightly.py`: `RETENTION_DAYS = 7` (comment: must match the web) and
    `RATE_LIMIT_MAX_AGE = timedelta(minutes=10)`.
  - Windows: `storefront/views.py` `WINDOW_SECONDS = 600`, `dashboard/views.py` `WRITE_WINDOW_SECONDS = 600`,
    `accounts/views.py` `SIGN_IN_WINDOW_SECONDS = 60`.
  - Web: `apps/web/src/content/site.ts` line `export const RETENTION_DAYS = 7;`.
- The existing pattern for one window: `accounts/tests/test_login.py:238`
  `assert nightly.RATE_LIMIT_MAX_AGE.total_seconds() >= views.SIGN_IN_WINDOW_SECONDS`.
- The existing pattern for reading a repo file: `storefront/tests/test_contract.py:24`
  `FIXTURES = Path(settings.BASE_DIR).parent.parent / "docs/api/fixtures"`.
- Add to `test_nightly.py` (keep its imports style; it already imports `nightly`, `ratelimit`, `RateLimit`, `NOW`,
  `UTC`, `timedelta`):
  ```python
  def test_every_rate_limit_window_fits_the_prune_age():
      # import storefront.views, dashboard.views, accounts.views as modules
      windows = (storefront_views.WINDOW_SECONDS, dashboard_views.WRITE_WINDOW_SECONDS,
                 accounts_views.SIGN_IN_WINDOW_SECONDS)
      assert max(windows) <= nightly.RATE_LIMIT_MAX_AGE.total_seconds()

  def test_retention_days_match_the_privacy_page():
      site = (Path(settings.BASE_DIR).parent.parent / "apps/web/src/content/site.ts").read_text()
      match = re.search(r"^export const RETENTION_DAYS = (\d+);$", site, re.MULTILINE)
      assert match and int(match.group(1)) == nightly.RETENTION_DAYS
  ```
  And a `@pytest.mark.django_db` test, `test_prune_keeps_a_window_exactly_at_the_max_age`:
  `utc_now = NOW.astimezone(UTC)`, `cutoff = utc_now - nightly.RATE_LIMIT_MAX_AGE`. Create
  `RateLimit(key="edge", window_start=cutoff, count=1)` and `RateLimit(key="old", window_start=cutoff -
  timedelta(seconds=1), count=1)`. Run `ratelimit.prune(older_than=nightly.RATE_LIMIT_MAX_AGE, now=utc_now)` (it
  deletes `window_start < cutoff`, `core/ratelimit.py:54-59`). Assert only `"edge"` remains. Check the model's fields
  in `core/models.py` first.
- `turbo.json` `tasks.test.inputs` is `["$TURBO_DEFAULT$", "$TURBO_ROOT$/docs/api/fixtures/**"]`. Append
  `"$TURBO_ROOT$/apps/web/src/content/site.ts"`, so a change there re-runs the backend tests.
- `docs/runbook.md` `## Demo data and nightly job` (around line 426-500): where it describes running the job by hand,
  add a sentence and command. Before `gcloud run jobs execute cb-nightly`, check that no execution is running:
  `gcloud run jobs executions list --job cb-nightly --region asia-southeast1 --limit 1`. Two overlapping runs can
  leave a partial demo reseed, which the next night's run repairs. There's no lock, because session advisory locks
  don't hold through Neon's transaction-mode pooler. Match the section's wording style.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change any constant.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm format:check
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
grep -n 'executions list' docs/runbook.md
```
- Temporarily changing `RETENTION_DAYS` in `site.ts` to 8 makes `test_retention_days_match_the_privacy_page` fail.
  Revert it.
