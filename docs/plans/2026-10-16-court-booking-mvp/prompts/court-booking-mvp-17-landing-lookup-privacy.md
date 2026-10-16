---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 17
unit: CBS-7
status: todo
model: sonnet
effort: high
depends_on: [16]
parallel_group: Q
files:
  create:
    - apps/web/app/booking/page.tsx
    - apps/web/app/privacy/page.tsx
    - apps/web/app/staff/route.ts
    - apps/web/src/lib/booking/lookup.ts
    - apps/web/src/components/booking/lookup-form.tsx
    - apps/web/src/content/__tests__/site.test.ts
  modify:
    - apps/web/app/page.tsx
    - apps/web/src/content/site.ts
    - apps/web/.env.example
  delete: []
---
# 17 · Landing page, booking lookup, privacy notice and staff link

## Task
Finish the storefront for business owners viewing the demo:
- A real **landing page**: hero, sports and rates, how it works, hours, FAQ, and a "See the owner's side" link.
- **`/booking`**: look up a booking by reference plus email.
- **`/privacy`**: an RA 10173 notice that matches exactly what is stored.
- **`/staff`**: a redirect to the Django dashboard.
- A test that ties the site copy to the backend catalog fixture.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Web app: `apps/web` (Next.js 16.4, Tailwind v4 tokens
  `--color-ink/paper/court/clay/line`; `src/content/site.ts` exports `SITE` with `name`, `tagline`, `description`
  and `testModeNotice`, plus `getSiteUrl()`).
- Server-only API client in `src/lib/api/client.ts`: `getCatalog()`, `lookupBooking({reference, email, clientIp})`
  (404 → `ApiError(404, "not_found")`, 429 → `rate_limited`), `clientIpFrom(headers)`, `ApiError`. Types are in
  `src/lib/api/schemas.ts`. `src/lib/booking/params.ts` has `formatPeso` and `formatHour`.
- Facts the copy must state, and **what the backend stores** (it must match `/privacy`):
  - Open daily 07:00–23:00. Book up to 7 days ahead, 1–3 hours, on the hour.
  - 2 basketball courts (full or half; volleyball full court only), 4 tennis courts, 12 badminton/pickleball courts.
  - Peak is weekdays from 5 PM and all day on weekends.
  - Payment is PayMongo **test mode** (card, GCash, Maya, GrabPay). The slot is held 20 minutes while you pay.
  - The app stores your name, email and mobile, the booking details, the payment reference and method, and the
    time you gave consent. It doesn't store card or wallet details; PayMongo handles those.
  - Visitor bookings are **anonymized by the nightly job once 7 days have passed since the booking ended** (so within
    8 days): name, email and mobile are removed, and the
    court, time and amount stay for the venue's statistics. Demo bookings use fake `@example.com` people. No email
    or SMS is sent.
  - The app's own logs keep the request path without query strings, and no IP. **Google Cloud Run's platform request
    logs** (Cloud Logging) do record the IP address, user agent and URL, kept for 30 days by default. Say so plainly.
    Rate-limit counters keep a one-way hash of the IP, which the nightly job deletes within a day.
- **`src/content/site.ts`**: add `HOURS = { open: 7, close: 23 }`, `WINDOW_DAYS = 7`, `MAX_HOURS = 3`,
  `RETENTION_DAYS = 7`, and `getDashboardUrl()` (reads `DASHBOARD_URL` through `createEnv` per call). Add a FAQ array.
- **`src/content/__tests__/site.test.ts`**: read `docs/api/fixtures/catalog.json` from the repo root. Assert that
  `HOURS`, `WINDOW_DAYS` and `MAX_HOURS` equal the fixture's `hours`, `window_days` and `max_hours`, and that
  `SITE.name` equals `venue.name`. This is the drift guard between the copy and the backend rules.
- **`app/page.tsx`** (landing): a hero (name, tagline, "Book a court" → `/book`, a "Fictional venue" tag).
  - A **Sports & rates** section, streamed inside `<Suspense>`: a card per sport with court count and off-peak/peak
    rates from `getCatalog()`. If the API fails, show "See live rates on the booking page" and nothing else, so the
    landing page never breaks when the backend is cold or down.
  - How it works: pick → hold 20 min → pay → show your reference. An hours block, and the FAQ (`<details>`).
  - A **For venue owners** band: "See what staff see: live schedule, walk-ins, revenue", linking to `/staff`.
  - Responsive at 375, 768 and 1280 px, with no horizontal scroll.
- **`src/lib/booking/lookup.ts`** (`"use server"`), `lookup(prev, formData)`:
  - Validate with zod: the reference matches `^KC-[0-9A-HJKMNP-TV-Z]{6}$` after trimming and uppercasing; the email is
    a valid email. Then `lookupBooking` with `clientIpFrom(await headers())`.
  - Return the summary, or a fixed message: not found → "No booking matches that reference and email."; rate limited
    → "Too many lookups. Try again in a few minutes."; anything else → "Lookup is unavailable right now."
  - Never log the inputs.
- **`src/components/booking/lookup-form.tsx`** (`"use client"`, `useActionState`) renders the form and the result:
  status badge, court, date and time, amount. **`app/booking/page.tsx`** hosts it, with the title "Find your booking".
- **`app/privacy/page.tsx`**: a plain-language notice covering who (the fictional Kalaro Courts portfolio demo), what
  is collected and why, the legal basis (consent), sharing (PayMongo for payment, test mode), retention as above, your
  rights under the Data Privacy Act of 2012 (RA 10173), and a note that it's a demo. It must use the same facts as
  the list above, and nothing more.
- **`app/staff/route.ts`**: `GET` → `Response.redirect(getDashboardUrl(), 307)`. If the env is missing → 500 with plain
  text "Staff dashboard isn't configured." Copy the pattern from
  `/Users/alessandrocruz/Code/fun-run-website/apps/web/app/organizer/route.ts` (read only).
- **`.env.example`**: add `DASHBOARD_URL=http://localhost:8000/dashboard/` with a comment saying only `/staff` reads it.
- Review constraints: **personal data** (`/privacy` must match the storage and retention above); **the build reads no
  env**; **the test-mode banner is on every page**; **secrets stay on the server** (the lookup uses a server action).

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Promise anything in `/privacy` that the backend doesn't do (no email, no account deletion form).
- Put reference or email in the URL. The lookup is a POST server action.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
pnpm format:check && pnpm lint && pnpm typecheck
pnpm --filter @cb/web test
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build
```
- `SITE_URL=http://localhost:3000 DASHBOARD_URL=http://localhost:8000/dashboard/ pnpm --filter @cb/web start` (no
  backend running): `/` still renders, with the rates fallback; `/staff` gives a 307 to the dashboard; `/privacy`
  mentions 7 days; and every page shows the banner.
