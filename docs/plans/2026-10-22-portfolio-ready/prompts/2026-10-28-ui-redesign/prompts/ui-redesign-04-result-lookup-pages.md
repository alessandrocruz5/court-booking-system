---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 04
unit: CBS-17
status: todo
model: opus
effort: medium
depends_on: [03]
parallel_group: A
files:
  create:
    - apps/web/src/components/booking/copy-reference.tsx
    - apps/web/src/components/booking/__tests__/copy-reference.test.tsx
  modify:
    - apps/web/app/book/success/page.tsx
    - apps/web/app/book/cancelled/page.tsx
    - apps/web/app/booking/page.tsx
    - apps/web/src/components/booking/lookup-form.tsx
    - apps/web/app/book/__tests__/result-pages.test.tsx
  delete: []
---
# 04 · Success, cancelled and Find booking pages

## Task
Restyle the result pages and the lookup to the spec. The confirmed state gets the dark reference card with a Copy button.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Booking.dc.html` (done and find screens).
- `app/book/success/**` is **high-stakes**: change markup only.
  - Status still comes only from `checkout/confirm`, and `?ref=` only picks among the visitor's own cookie entries (`pickCheckout`).
  - Don't touch the data path.
- **Leave out the prototype's "A copy was sent to {email}."** No email is sent (FAQ, `/privacy`).
- `copy-reference.tsx` (`"use client"`): a button that calls `navigator.clipboard.writeText(reference)` and shows "Copied" for 2 s, with `aria-live="polite"`.
  - Test it: the click writes to a mocked clipboard and the label changes.
- Success rows: Court, Sport (with coverage), Date, Time, Amount paid, and Payment method. Take payment method from the payload if present; otherwise omit the row. Don't invent "Card".
- Pending, needs-refund and not-found states: same copy and logic, in the new card styles (warn tokens).
- `/book/cancelled`: same shell, copy unchanged.
- `/booking` and `lookup-form.tsx`: the reference input is mono, uppercase, placeholder `KC-XXXXXX`. Not-found uses the spec's warn copy. Found is the court-bordered card.
  - Keep the lookup's server action, rate limiting and error codes.
- `result-pages.test.tsx`: update only text and markup assertions changed here. Add one: the confirmed page contains no "sent to".

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
pnpm --filter @cb/web lint && pnpm --filter @cb/web typecheck && pnpm --filter @cb/web test && pnpm --filter @cb/web build
! grep -rn 'sent to' apps/web/app/book/success/page.tsx
```
