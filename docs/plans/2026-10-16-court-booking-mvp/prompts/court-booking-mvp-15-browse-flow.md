---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 15
unit: CBS-7
status: done
model: sonnet
effort: high
depends_on: [14]
parallel_group: O
files:
  create:
    - apps/web/app/book/page.tsx
    - apps/web/app/book/loading.tsx
    - apps/web/src/lib/booking/params.ts
    - apps/web/src/lib/booking/__tests__/params.test.ts
    - apps/web/src/components/booking/sport-picker.tsx
    - apps/web/src/components/booking/duration-picker.tsx
    - apps/web/src/components/booking/date-strip.tsx
    - apps/web/src/components/booking/availability-grid.tsx
  modify: []
  delete: []
---
# 15 · Booking browse flow

## Task
Build `/book`, a fast, phone-first flow. The customer picks a sport (and full or half court for basketball), a duration
(1–3 h), one of the next 7 dates, then a court and start time. The state lives in the URL, every step is a plain
link (it works without JavaScript), and availability comes from the backend on every request.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Web app: `apps/web` (Next.js 16.4 App Router, React 19,
  Tailwind v4 with tokens `--color-ink/paper/court/clay/line` in `app/globals.css`, `@/*` → `src/*`).
  **Read `node_modules/next/dist/docs/` for `searchParams` (a Promise in Next 16) and Suspense streaming before writing.**
- The server-only API client is in `src/lib/api/client.ts`. It exports `getCatalog()`, `getAvailability({date, sport,
  coverage, hours})` and `ApiError(status, code)`. The types are in `src/lib/api/schemas.ts` (`Catalog`, `Availability`).
  - The catalog holds `hours.open` (7) and `hours.close` (23), `window_days` (7), `max_hours` (3), `peak`, and
    `sports[]` with `id`, `label`, `coverages` and `rates`.
  - Availability holds `courts[]`, each with `code`, `name` and `starts[]` of `{hour, price_centavos, peak}`.
- Business rules (the backend enforces them; the UI only offers valid choices): open 07:00–23:00; bookings 1–3 h on
  the hour; today through today + 6, Asia/Manila; basketball takes full or half; **volleyball is full court only**;
  badminton and pickleball use courts 1–12; tennis courts 1–4.
- **`src/lib/booking/params.ts`** (pure, tested):
  - `type BookingParams = { sport?, coverage, hours, date?, court?, start? }`.
  - `parseBookingParams(searchParams, catalog, today: string)`. Unknown or invalid values fall back to undefined or
    the defaults: coverage `full`, hours `1`. A coverage the sport doesn't allow becomes `full`. Hours are clamped to
    1..`max_hours`. A date outside the window is dropped.
  - `bookingHref(params, patch)` builds `/book?…`. Changing the sport clears the court and start. Changing the date or
    duration clears the start.
  - `manilaToday(now = new Date()): string` returns `YYYY-MM-DD` via `Intl.DateTimeFormat` with `timeZone: "Asia/Manila"`.
    `windowDates(today, days)` lists the window's dates.
  - `formatPeso(centavos)` gives `₱1,200`. `formatHour(h)` gives `7 AM` / `10 PM`.
- **`app/book/page.tsx`** (a server component, dynamic). Await `searchParams`, then `getCatalog()`, then parse. Render:
  1. A step header with a breadcrumb: Sport → Time → Details.
  2. `<SportPicker>`: cards for the 5 sports, each with a label, court count and an "from ₱X/h" off-peak rate. For
     basketball, a Full/Half toggle; volleyball shows "Full court".
  3. `<DurationPicker>`: 1, 2 or 3 hours.
  4. `<DateStrip>`: 7 day chips such as "Today", "Sat 18". Mark weekends as peak all day.
  5. `<AvailabilityGrid>`, inside `<Suspense>` with a skeleton, so the shell paints at once even when the backend is
     cold-starting. One card per court lists its start times as chips (`6 PM · ₱1,600`), with peak chips in the clay
     accent. Each chip links to `bookingHref({court, start})`.
     - An empty state for no free times.
     - On `ApiError`, a friendly "We couldn't load times. Try again." with a retry link. Never show the error detail.
  6. When `court` and `start` are set, show a "Selected" summary. Prompt 16 renders the details form below it; leave
     a clearly marked spot.
  - Accessibility: chips are links with `aria-current` when selected, and focus styles are visible. It must work at
    375 px with no horizontal page scroll.
- **`app/book/loading.tsx`**: a skeleton of the step header and pickers. The page awaits `getCatalog()` before it
  renders, so without this a cold backend blocks the whole page; with it, the layout, banner and skeleton paint at once.
- `generateMetadata`: title "Book a court".
- **Tests** (`params.test.ts`):
  - Defaults apply.
  - Volleyball with half becomes full.
  - Hours 9 is clamped to 3.
  - Today + 7 is dropped.
  - Changing the sport clears the court and start.
  - `manilaToday` at 2026-10-16T17:30:00Z gives `2026-10-17` (01:30 Manila time).
  - `formatPeso(160000)` is `₱1,600`.
- Review constraints: **the build reads no env**: the page is dynamic and only calls the client inside the request.
  **API responses aren't cached**: the client already uses `no-store`, and you don't add caching. **Every page shows
  the test-mode banner**: the root layout handles it.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Make any component a client component unless it truly needs to be. The flow works as links. Never import the API
  client into a `"use client"` file.
- Add the details form or server actions. That's prompt 16.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
pnpm format:check && pnpm lint && pnpm typecheck
pnpm --filter @cb/web test
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build
```
- Run it locally: backend on 8000 (`pnpm --filter @cb/backend dev`, migrated local DB) and web on 3000 with `API_URL`
  and `INTERNAL_API_TOKEN` in `.env.local`. Open `/book?sport=basketball&coverage=half&hours=2&date=<today>`: it shows
  both basketball courts with start chips and prices. Switching to volleyball removes the half option. It works with
  JavaScript disabled.
