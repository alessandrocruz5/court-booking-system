---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 11
unit: CBS-16
status: done
model: opus
effort: high
depends_on: [10]
parallel_group: E
files:
  create: []
  modify:
    - apps/web/src/lib/booking/actions.ts
    - apps/web/src/lib/booking/__tests__/actions.test.ts
    - CLAUDE.md
  delete: []
---
# 11 · `startCheckout` writes per-booking entries; bad-URL release; `releaseHold` by ref

## Task
1. `startCheckout` adds this checkout to the `cb_checkout` cookie as a `reference → session` entry (new format, up to
   3) instead of overwriting it.
2. On its defensive bad-checkout-URL branch, it releases the hold it just created before returning the error.
3. `releaseHold` (the cancel page's "Release my hold" form action) releases the entry named by the form's `ref`, and
   reloads `/book/cancelled?ref=<ref>`.
4. Update `CLAUDE.md`'s cookie coupling line and the payment-status constraint wording.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Web: `apps/web` (Next.js 16, TypeScript, zod, vitest).
- Prompt 10 added `src/lib/booking/checkout-cookie.ts`: `CHECKOUT_COOKIE`, `MAX_CHECKOUTS`, `isReference`,
  `parseCheckouts`, `addCheckout(value, { reference, sessionId })` and `pickCheckout(value, ref)`. Read it first. The
  result pages already read both formats and pass `?ref=`. The backend's success/cancel URLs carry `?ref=<reference>`
  (prompt 09).
- Review constraints:
  - "Payment status comes only from the server."
  - No personal data in logs: log error codes only (`checkout.create_failed <code>`, `checkout.release_failed
    <code>`, `checkout.bad_checkout_url`).
  - The internal API token never reaches a client component.
- `src/lib/booking/actions.ts` (read it whole):
  - Delete the local `const CHECKOUT_COOKIE` and its comment, and import from the module. The file stays
    `"use server"`, exporting only async functions.
  - Cookie set (~:200): `const store = await cookies(); store.set(CHECKOUT_COOKIE, addCheckout(store.get(CHECKOUT_COOKIE)?.value,
    { reference: created.reference, sessionId: created.checkout_session_id }), { …same options… })`. Keep `httpOnly`,
    `sameSite: "lax"`, `secure` in production, `path: "/book"`, `maxAge: 86_400`.
  - Bad URL branch (`if (!isPayMongoCheckout(created.checkout_url))`): keep the log, then a best-effort
    `await releaseCheckout(created.checkout_session_id)` in a try/catch that rethrows non-`ApiError`s and logs
    `checkout.release_failed ${error.code}` for an `ApiError`. Then return `{ message: UNAVAILABLE, values }`. Still no
    cookie.
  - `releaseHold(formData: FormData)`: `const ref = formData.get("ref")`, and `const sessionId =
    pickCheckout(cookieValue, ref)`. Release as today, then `redirect(isReference(ref) ?
    \`/book/cancelled?ref=${ref}\` : "/book/cancelled")`, outside any try/catch. Update its docstring.
- `src/lib/booking/__tests__/actions.test.ts` (read it whole; it mocks `next/headers` `cookies()` with `set:
  cookieSet` and `get("cb_checkout")`, and `createBooking`/`releaseCheckout`):
  - The success test now expects the cookie value `"<reference>.cs_test_abc"` (the reference from the test's created
    response), with the same options.
  - Add: an existing cookie with 3 entries → the new entry first, the oldest dropped. The bad-URL branch →
    `releaseCheckout` called once with the session ID, no cookie set, `UNAVAILABLE`; `releaseCheckout` throwing
    `ApiError` there still returns `UNAVAILABLE`.
  - `releaseHold` with `ref` → releases that entry and redirects to `/book/cancelled?ref=…`. Without `ref` → releases
    the newest and redirects to `/book/cancelled`. A legacy bare cookie still works.
  - Update the existing `releaseHold` test to pass a `FormData`.
- `CLAUDE.md`:
  - `## Hidden coupling`, the "Checkout cookie" bullet: say it holds up to 3 `REF.session` entries (newest first),
    defined in `apps/web/src/lib/booking/checkout-cookie.ts`, written by `startCheckout` in
    `apps/web/src/lib/booking/actions.ts`, and read by `app/book/{success,cancelled}`, and that the backend's
    success/cancel URLs (`storefront/views.py`) carry `?ref=`.
  - `## Review constraints`, "Payment status comes only from the server" bullet (the user approved this wording on
    2026-10-21): after "URL parameters are never
    trusted.", add "(`?ref=` on `/book/success` and `/book/cancelled` only picks one of the visitor's own cookie
    entries)". Change nothing else.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change the cookie options, the form validation, or the API client.
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
docker build -f apps/web/Dockerfile -t cb-web:local .
! grep -rn 'const CHECKOUT_COOKIE' apps/web/src apps/web/app
```
