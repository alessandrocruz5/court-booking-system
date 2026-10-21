---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 10
unit: CBS-16
status: done
model: opus
effort: high
depends_on: [09]
parallel_group: E
files:
  create:
    - apps/web/src/lib/booking/checkout-cookie.ts
    - apps/web/src/lib/booking/__tests__/checkout-cookie.test.ts
  modify:
    - apps/web/app/book/success/page.tsx
    - apps/web/app/book/cancelled/page.tsx
    - apps/web/app/book/__tests__/result-pages.test.tsx
  delete: []
---
# 10 · Checkout cookie module; result pages pick their own session

## Task
1. Add a plain module that owns the `cb_checkout` cookie's name and format: up to 3 `reference → session` entries,
   newest first.
2. Make `/book/success` and `/book/cancelled` use `?ref=` to pick **their own** entry from the cookie, and accept
   both the old (bare session ID) and the new format.
3. Make the success page's `needs_refund` copy name no cause.
The writer (`startCheckout`) moves to the new format in prompt 11. Until then, the pages keep working with the old
cookie.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Web: `apps/web` (Next.js 16, React 19, TypeScript, zod, vitest).
  Package `@cb/web`.
- Review constraints:
  - "Payment status comes only from the server … URL parameters are never trusted." `ref` only selects among the
    sessions already in the visitor's own httpOnly cookie. The status always comes from `confirmCheckout` /
    `releaseCheckout`. A `ref` that isn't in the cookie selects **nothing**, never another entry.
  - No personal data in logs: log only error codes, as the pages do now.
- Hidden coupling: the checkout cookie `cb_checkout` (path `/book`) is set in `src/lib/booking/actions.ts` and read by
  `app/book/{success,cancelled}`. Today both pages redefine `const CHECKOUT_COOKIE = "cb_checkout"`, because
  `actions.ts` is `"use server"` and may only export async functions. The new module ends that duplication.
- Formats: a backend session ID matches `^cs_[A-Za-z0-9]+$` (`apps/backend/payments/paymongo.py:25`), but web tests
  use IDs like `cs_test_abc`, so accept `^cs_\w{1,128}$` on the web. A reference matches
  `^KC-[0-9A-HJKMNP-TV-Z]{6}$` (`apps/backend/bookings/references.py`). The backend's success/cancel URLs carry
  `?ref=<reference>` (prompt 09).
- `src/lib/booking/checkout-cookie.ts` (no `"use server"`, no React; pure functions):
  ```ts
  export const CHECKOUT_COOKIE = "cb_checkout";
  export const MAX_CHECKOUTS = 3;
  export type CheckoutEntry = { reference: string | null; sessionId: string };
  export function isReference(value: unknown): value is string;
  /** "KC-AAAAAA.cs_x|KC-BBBBBB.cs_y" (newest first) → entries; a legacy bare "cs_x" → one entry with
   *  reference null; malformed parts are dropped. */
  export function parseCheckouts(value: string | undefined): CheckoutEntry[];
  /** Prepend `entry`, drop any older entry with the same reference or session, keep MAX_CHECKOUTS. */
  export function addCheckout(value: string | undefined, entry: { reference: string; sessionId: string }): string;
  /** A well-formed `ref`: that entry's session; if no entry has it, a legacy (reference-null) entry's session
   *  if there is one (the rollout window: new backend URL, old web cookie), else undefined. Never another
   *  referenced entry. No or malformed `ref`: the newest entry's session (also the legacy value). */
  export function pickCheckout(value: string | undefined, ref: unknown): string | undefined;
  ```
  Write a module docstring that explains the format, the bound, and why `ref` can't change a result. `.` and `|` can't
  appear in a reference or session ID, so they're safe separators.
- Pages (read both whole first). Next 16 page props: `{ searchParams: Promise<Record<string, string | string[] |
  undefined>> }`. Read only `ref`.
  - `app/book/success/page.tsx`:
    - Delete the local `CHECKOUT_COOKIE`, and import from the module.
    - `const sessionId = pickCheckout(cookie, (await searchParams).ref)`.
    - Rewrite the docstring: replace "this page never reads `searchParams`" with the rule above.
    - `CheckAgain` links to `/book/success?ref=<ref>` when `ref` is a valid reference (`encodeURIComponent`), else
      `/book/success`.
    - `needs_refund` copy: eyebrow "Refund due", and a cause-neutral title and body. For example: title "Your booking
      didn't go through.", body "We received your payment, but this booking was cancelled or its slot was taken. Our
      staff will refund you (test mode)."
  - `app/book/cancelled/page.tsx`:
    - Same cookie and `ref` handling.
    - The prefetch branch's "Release my hold" form adds `<input type="hidden" name="ref" value={ref} />` when `ref` is
      valid. `releaseHold` starts reading it in prompt 11; today it ignores form data, which is harmless.
    - "See your booking" and "Check again" keep the `?ref=`.
    - The no-entry path stays as today (the page treats "no cookie" as `released`, without calling the backend).
- Tests:
  - `src/lib/booking/__tests__/checkout-cookie.test.ts`: parse (v2, legacy, junk, empty); `addCheckout` (prepend,
    dedupe by reference and session, cap 3, from a legacy value); `pickCheckout` (matching `ref`; a valid but unknown
    `ref` with only referenced entries → undefined; a valid `ref` with a legacy bare cookie → the legacy session; no
    `ref` → newest; malformed `ref` → newest; array `ref` → newest).
  - `app/book/__tests__/result-pages.test.tsx` (read it whole; it mocks `next/headers` `cookies().get("cb_checkout")`
    and renders pages with `render(page, props)`):
    - Keep every existing test. Pass `searchParams` where needed; the forged-`searchParams` test must still prove a
      forged `status`/`reference` changes nothing.
    - Add: two entries plus `?ref=` of the older → `confirmCheckout` is called with the older entry's session;
      a valid unknown `ref` → `not_found` and `confirmCheckout` is not called; no `ref` → newest; the legacy cookie
      still confirms; the cancelled page with `?ref=` of A releases A's session only; the prefetch form carries the
      hidden `ref`; the `needs_refund` copy.

## Do not
- Touch files outside the `files` list (`actions.ts` included). If you must, stop and report why.
- Read any search param other than `ref`, or let `ref` reach `confirmCheckout`/`releaseCheckout` except through
  `pickCheckout`.
- Export the cookie name from a `"use server"` file.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/court-booking-system
pnpm format:check
pnpm --filter @cb/web lint
pnpm --filter @cb/web typecheck
pnpm --filter @cb/web test
pnpm --filter @cb/web build
! grep -rn 'const CHECKOUT_COOKIE' apps/web/app
```
