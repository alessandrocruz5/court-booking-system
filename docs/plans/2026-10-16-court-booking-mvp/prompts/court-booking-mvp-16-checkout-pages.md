---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 16
unit: CBS-7
status: todo
model: opus
effort: high
depends_on: [15]
parallel_group: P
files:
  create:
    - apps/web/src/lib/booking/actions.ts
    - apps/web/src/lib/booking/__tests__/actions.test.ts
    - apps/web/src/components/booking/details-form.tsx
    - apps/web/app/book/success/page.tsx
    - apps/web/app/book/cancelled/page.tsx
  modify:
    - apps/web/app/book/page.tsx
  delete: []
---
# 16 · Checkout, success and cancelled pages

## Task
Finish the customer booking flow. The guest enters name, email and mobile and gives consent. A server action asks
the backend for a 20-minute hold plus a PayMongo test checkout, stores the checkout session ID in an httpOnly cookie,
and redirects to PayMongo. `/book/success` and `/book/cancelled` work out the result **from the server**, using
only the cookie and never URL parameters.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Web app: `apps/web` (Next.js 16.4, React 19, zod 4).
  **Read `node_modules/next/dist/docs/` on server actions, `useActionState`, `cookies()` and `redirect()` first.**
- Pattern reference, read only: `/Users/alessandrocruz/Code/fun-run-website/apps/web/src/lib/registration/actions.ts`
  and `src/components/registration-form.tsx` (a server action with a client form via `useActionState`, an httpOnly
  checkout cookie, then a redirect to PayMongo), and `app/register/success/page.tsx` (the result comes from the cookie
  and a server lookup, with fixed messages).
- Already there:
  - `src/lib/api/client.ts` (server only): `createBooking({court, sport, coverage, date, startHour, hours, customer:
    {name, email, mobile}, consent, clientIp}) -> {reference, checkoutUrl, checkoutSessionId, holdExpiresAt,
    priceCentavos}`, `confirmCheckout(id)`, `releaseCheckout(id)`, `clientIpFrom(headers)` and `ApiError(status, code)`.
    Error codes: `invalid_request` (+`fields`), `slot_taken`, `rate_limited`, `too_many_holds`, `payments_unavailable`,
    rule codes, and `unavailable`.
  - `src/lib/booking/params.ts`: `parseBookingParams`, `bookingHref`, `formatPeso`, `formatHour`.
  - `app/book/page.tsx` has a marked spot for the details step, which shows when `court` and `start` are selected.
- **`src/lib/booking/actions.ts`** (`"use server"`):
  - `export const CHECKOUT_COOKIE = "cb_checkout"`.
  - `startCheckout(prev, formData)`. Validate with zod:
    - name: 2–80 characters, trimmed.
    - email.
    - mobile: `^(\+63|0)9\d{9}$`, with spaces and dashes stripped first.
    - consent: must be `"on"`.
    - the hidden fields court, sport, coverage, date, start and hours.

    On a validation error, return `{ fieldErrors, values: {name, email, mobile} }` (re-shown in the form, never logged).
    Then:
    - `const clientIp = clientIpFrom(await headers())`, then `createBooking(...)`.
    - On success, set the cookie `cb_checkout = checkoutSessionId` with `httpOnly`, `sameSite: "lax"`,
      `secure: process.env.NODE_ENV === "production"`, `path: "/book"` and `maxAge: 86400`. Then
      `redirect(checkoutUrl)`, **only if** the URL is `https:` on `checkout.paymongo.com`; otherwise return the
      `unavailable` message.
    - `ApiError` → return one fixed message per code:
      - `slot_taken`: "Someone just booked that time. Pick another slot."
      - `rate_limited` / `too_many_holds`: "Too many bookings in progress. Finish or cancel one, then try again."
      - `payments_unavailable` / `unavailable`: "Payments are unavailable right now. Please try again shortly."
      - anything else: "Something went wrong. Please try again."

      Keep the `values`.
    - Log only the error code, never form values (RA 10173).
- **`src/components/booking/details-form.tsx`** (`"use client"`): `useActionState(startCheckout, …)`.
  - It shows a summary passed as props (court name, sport, coverage, date, time range, price), so the server page
    computes the price from availability and nothing is trusted from the client: the backend re-quotes.
  - Inputs: name (`autoComplete="name"`), email, mobile (`inputMode="tel"`, placeholder `0917 123 4567`), and a consent
    checkbox labelled "I agree to the [privacy notice](/privacy) and to Kalaro Courts storing my name, email and mobile
    for this booking." Hidden inputs carry the selection.
  - A submit button with a pending state, inline errors with `aria-describedby`, and a note: "You'll pay on PayMongo's
    test checkout. Your slot is held for 20 minutes."
  - Never import the API client here.
- **`app/book/page.tsx`**: when `court` and `start` are valid **and** the start appears in the current availability for
  that court, render `<DetailsForm>` with the summary. Otherwise render a "That time is no longer available" message
  with a link back.
- **`app/book/success/page.tsx`** (dynamic): read `cb_checkout` from `cookies()`, then `confirmCheckout(id)` (no cookie
  → `not_found`). Render by status, with fixed copy:
  - `confirmed`: a big reference (`KC-…`), court, sport and coverage (and half), date, time range, amount, payment
    method, and "Show this reference at the front desk." Add a link to `/booking`.
  - `pending`: "Your payment is still processing." plus a "Check again" link (`/book/success`).
  - `needs_refund`: "Your payment arrived after your hold expired and the slot was taken. Our staff will refund you
    (test mode)."
  - `not_found`: "We couldn't find a booking in this browser." plus a link to `/booking`.
  - `unavailable`: "We couldn't check right now. Try again in a moment." plus "Check again".
  - `expired` / `cancelled` (added in CBS-6: the hold lapsed or was released and no payment has arrived yet): "Your
    hold ended before we received payment. If you completed payment, it may still go through." plus "Check again"
    (`/book/success`) and a link back to `/book`. Never say the booking definitely wasn't made: a late payment (the
    webhook can land seconds after the redirect) still confirms it or re-claims the slot.

  It **never reads `searchParams`**. A URL like `/book/success?status=paid` changes nothing.
- **`app/book/cancelled/page.tsx`**: read the cookie, then `releaseCheckout(id)` (no cookie → treat as released). Map
  each status to copy:
  - `released`: "Your hold was released. No payment was taken." plus "Pick another time" (`/book`).
  - `already_paid`: "This booking is already paid." plus a link to `/book/success`.
  - `not_found`.
- **Tests** (`actions.test.ts`; mock `@/lib/api/client`, `next/headers` and `next/navigation`, as in fun-run's actions tests):
  - Invalid input returns `fieldErrors` and never calls `createBooking`.
  - `consent` is required.
  - Success sets the cookie with `httpOnly`, `path: "/book"` and `sameSite: "lax"`, then redirects to the checkout URL.
  - A non-PayMongo checkout URL doesn't redirect.
  - `slot_taken` gives its fixed message, with values kept.
  - The client IP passed is the rightmost `x-forwarded-for` entry.
  - Nothing logs the email (spy on `console`).
- Review constraints:
  - **Payment status only from the server**: the cookie plus a backend check, never URL parameters.
  - **Secrets stay on the server**: no client import of the API client.
  - **Personal data**: no form values in logs.
  - **Test-mode banner**: the layout handles it.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Read `searchParams` on the success or cancelled pages, or show anything taken from the URL.
- Store anything but the checkout session ID in the cookie.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
pnpm format:check && pnpm lint && pnpm typecheck
pnpm --filter @cb/web test
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build
```
- With the local backend (`PAYMONGO_SECRET_KEY=sk_test_…` in `apps/backend/.env`) and web running, book a tennis court:
  you land on `checkout.paymongo.com`. Cancel there → `/book/cancelled` says the hold was released, and the slot shows
  as free again. `curl -s 'localhost:3000/book/success?status=confirmed'` without the cookie shows the `not_found` copy.
