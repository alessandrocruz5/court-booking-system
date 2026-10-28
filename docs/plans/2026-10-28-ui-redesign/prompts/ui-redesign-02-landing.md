---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 02
unit: U1
status: todo
model: sonnet
effort: medium
depends_on: [01]
parallel_group: A
files:
  create:
    - apps/web/src/components/landing/free-tonight.tsx
    - apps/web/src/components/landing/__tests__/free-tonight.test.tsx
  modify:
    - apps/web/app/page.tsx
  delete: []
---
# 02 · Landing: hero with Free tonight, rates table, FAQ accordion

## Task
Rebuild `app/page.tsx` to the spec's Landing section.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Booking.dc.html` (home screen).
- Keep the copy from `SITE`, `FAQ`, `HOURS`, `WINDOW_DAYS`, `MAX_HOURS` and `HOLD_MINUTES` (`src/content/site.ts`). The prototype's FAQ text is a paraphrase: don't use it.
- **Rates**: rewrite the existing `Rates()` async component as a table, one row per (sport, coverage) from `catalog.sports[].rates`.
  - Each row shows the colour from `SPORT_COLORS`.
  - Peak prices render in clay.
  - The fallback link on error stays.
- **Free tonight** (`free-tonight.tsx`, an async server component inside `<Suspense fallback={null}>`): for each catalog sport, `getAvailabilityOnce(today, sport.id, "full", 1)` (`src/lib/api/client.ts`). Do the calls in parallel with `Promise.allSettled`.
  - The next free start is the smallest `starts[].hour` across courts, if any. Show "Next free {formatHour(h)}" or "Full tonight".
  - Each row links with `bookingHref` (`src/lib/booking/params.ts`) to that sport, today's date and that start. A full sport links to tomorrow.
  - If every call fails, render nothing.
  - Show "· peak rates" only when the first next-free hour is peak (weekend, or ≥ `PEAK_FROM_HOUR`).
- **FAQ**: `<details>`/`<summary>`, with the first item `open`. No client JS.
- **Owners CTA**: the link stays `/staff` with `prefetch={false}`.
- Test `free-tonight`: mock the client the way `app/book/__tests__/result-pages.test.tsx` mocks its API.
  - A sport with `starts` shows its earliest hour.
  - An empty sport shows "Full tonight" and links to tomorrow.
  - All calls rejecting renders nothing.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
pnpm --filter @cb/web lint && pnpm --filter @cb/web typecheck && pnpm --filter @cb/web test && pnpm --filter @cb/web build
```
