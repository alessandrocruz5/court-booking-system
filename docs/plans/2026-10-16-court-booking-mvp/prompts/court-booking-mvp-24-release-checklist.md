---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 24
unit: CBS-10
status: todo
model: haiku
effort: low
depends_on: [23]
parallel_group: X
files:
  create: []
  modify:
    - docs/runbook.md
    - README.md
  delete: []
---
# 24 · Pre-release checklist and demo guide

## Task
Append a pre-release owner checklist to `docs/runbook.md`, and a "Demo in 3 minutes" script to `README.md`. This is
documentation only. Every fact below is given; don't invent others.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Read `docs/runbook.md` first. It already has these
  sections: Local development, Neon (once), Cloud Run (once), Deploy, Roll back, Database roles and migrations,
  PayMongo (test mode), Demo data and nightly job, and Staff dashboard. Link to them by heading instead of repeating them.
- Append **`## Pre-release checklist`** to `docs/runbook.md` as a `- [ ]` list in this order:
  1. Neon: the `main` and `dev` branches exist; migrations ran as the owner on both; `cb_app_login` exists on both; and
     `psql "$DATABASE_URL" -c "CREATE TABLE x(id int)"` fails as `cb_app_login`.
  2. Secret Manager: all 6 secrets hold real values (no `pending` placeholders) and exactly 6 versions are active.
  3. GitHub variables are set: `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `BACKEND_URL`, `WEB_URL` and
     `DEMO_VIEWER_EMAIL`. The last Deploy run is green.
  4. `seed_staff` ran against `main`, and the demo button signs in as VIEWER.
  5. PayMongo (test mode): a webhook points to `$BACKEND_URL/webhooks/paymongo` for the event
     `checkout_session.payment.paid`, and its secret is in `cb-paymongo-webhook-secret`.
  6. An end-to-end test booking: book a tennis court on `$WEB_URL`, pay with the test card `4343 4343 4343 4345`, see
     the `KC-…` reference, find it on `/booking`, then see it on the dashboard schedule (signed in as owner).
  7. Webhook with the tab closed: start a booking, pay, close the tab before the redirect, and confirm the booking is
     confirmed on the dashboard within a minute.
  8. Cancel path: start a booking, click back or cancel on PayMongo, and confirm `/book/cancelled` says released and
     the slot is free again.
  9. **The `X-Forwarded-For` assumption.** Django's CSRF check runs first, so send the token, its cookie and a
     `Referer`. Put this block in the runbook as is:
     ```sh
     JAR=$(mktemp)
     TOKEN=$(curl -s -c "$JAR" "$BACKEND_URL/dashboard/login/" | sed -n 's/.*name="csrfmiddlewaretoken" value="\([^"]*\)".*/\1/p')
     for i in 1 2 3 4 5 6; do
       curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{redirect_url}\n' -X POST "$BACKEND_URL/dashboard/login/" \
         -H "Referer: $BACKEND_URL/dashboard/login/" -H "X-Forwarded-For: 10.0.0.$i" \
         --data-urlencode "csrfmiddlewaretoken=$TOKEN" -d 'email=nobody@example.com&password=wrong-password-123'
     done
     ```
     The first 5 lines end in `?error=invalid` and the 6th in `?error=rate_limited`, even though each request forged a
     different `X-Forwarded-For`. If the 6th says `invalid`, the rightmost-entry assumption in `core/http.py` is wrong:
     stop and fix it before sharing the demo. This locks your own IP out of sign-in for a minute.
     Then prove the rightmost entry is **per client**, not a shared front-end address. Within that same minute, from
     a second network (e.g. a phone hotspot), click **Explore the owner demo**: it must sign in. If it's rate-limited,
     every visitor shares one bucket, so stop and fix `core/http.py`. Repeat for the web: 11 lookups on
     `$WEB_URL/booking` from the first network (the 11th says "Too many lookups"), then one from the second network,
     which must answer normally.
  10. Cloud Scheduler `cb-nightly-trigger` exists. Run `gcloud run jobs execute cb-nightly --region asia-southeast1`
      once and check the logs show counts only (no emails).
  11. The free-tier check: `gcloud run services describe cb-web` and `cb-backend` show maxScale 1 and no minScale; the
      $1 budget alert exists; the Artifact Registry cleanup policy is active; and there are no uptime checks.
  12. The banner "Fictional venue · Test mode, no real payments" is visible on `/`, `/book`, `/privacy`, a 404 page,
      and `/dashboard/login/`.
- Append **`## Demo in 3 minutes`** to `README.md`, a script for showing a business owner:
  1. Open `$WEB_URL`, pick Basketball → Half court → 2 h → today → an evening slot (peak price shown).
  2. Pay with the test card. The reference appears.
  3. Open "See the owner's side" (`/staff`) → **Explore the owner demo**.
  4. Overview: today's utilization, revenue by sport, the peak-hour heatmap.
  5. Schedule: find the booking, add a walk-in on a free badminton court, and block a tennis court for "Resurfacing".
  6. Bookings: search by reference. Contact details are masked in the demo.

  Then add a short "What's fake" note: a fictional venue, PayMongo test mode, and demo customers using `@example.com`,
  reseeded nightly.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Include real URLs, keys, emails or project IDs. Use the `$WEB_URL` and `$BACKEND_URL` placeholders.
- Change any code.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
grep -n '## Pre-release checklist' docs/runbook.md
grep -n '## Demo in 3 minutes' README.md
grep -c '^- \[ \]' docs/runbook.md          # at least 12
! grep -nE 'sk_(test|live)_[A-Za-z0-9]{6,}|run\.app' README.md docs/runbook.md | grep -v '<PROJECT_NUMBER>'
```
