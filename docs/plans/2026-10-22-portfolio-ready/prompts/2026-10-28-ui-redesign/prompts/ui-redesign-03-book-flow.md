---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 03
unit: CBS-17
status: todo
model: sonnet
effort: high
depends_on: [02]
parallel_group: A
files:
  create:
    - apps/web/src/components/booking/step-card.tsx
    - apps/web/src/components/booking/booking-summary.tsx
    - apps/web/src/components/booking/court-picker.tsx
    - apps/web/src/components/booking/submit-overlay.tsx
  modify:
    - apps/web/app/book/page.tsx
    - apps/web/app/book/loading.tsx
    - apps/web/src/components/booking/sport-picker.tsx
    - apps/web/src/components/booking/date-strip.tsx
    - apps/web/src/components/booking/duration-picker.tsx
    - apps/web/src/components/booking/availability-grid.tsx
    - apps/web/src/components/booking/details-form.tsx
  delete: []
---
# 03 · /book: four step cards and a sticky summary

## Task
Restyle `/book` into the four step cards (Sport, Day & length, Start time, Your details), a sticky **Your booking** aside, and a bottom bar under 900px. Behaviour and data flow are unchanged.

## Context
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Booking.dc.html` (book screen). The prototype holds state on the client; **the repo stays URL-param driven.** Every choice is a `<Link href={bookingHref(...)}>`, as today.
- `book/page.tsx` already derives `step` from `params` ("sport" | "time" | "details"). Map it to the step circles:
  - Sport is done when `sport` is set.
  - Day & length is done when `sport` is set.
  - Start time is done when `court` and `start` are set.
  - Details is active when `selected`.
- `StepHeader` goes. Its eyebrow and H1 stay above the grid.
- `step-card.tsx`: a presentational wrapper (number, title, state, children, an optional right-side slot).
- **Sport** (`sport-picker.tsx`): tiles plus, for basketball, the coverage radio cards. "from ₱x/h" is the min of the sport's `off_peak` rates. The coverage sub-line uses the catalog rates.
- **Day & length** (`date-strip.tsx` + `duration-picker.tsx`, rendered in one card): seven day buttons with "Today" and PEAK (`weekendsPeak`), plus the segmented length control.
- **Start time** (`availability-grid.tsx`): tiles per start hour, aggregated across courts.
  - Price is the min `price_centavos` for that hour.
  - Availability shows "{n} free" or "1 court left".
  - Hours with no free court render as disabled "Booked".
  - Keep `AvailabilitySkeleton` and `LoadError`.
  - With a start selected, `court-picker.tsx` shows pills for each court free at that hour. If `params.court` is unset, the first one is linked as selected.
  - Today: show "Earlier times today have passed.".
- **Your details**: `DetailsForm` unchanged in behaviour (fields, consent, `startCheckout`). Restyle only.
  - Add `submit-overlay.tsx` (client, `useFormStatus`), rendered inside the form, showing "Slot held for {HOLD_MINUTES} minutes" / "Taking you to PayMongo's test checkout…".
  - Don't edit `src/lib/booking/actions.ts` (high-stakes).
- **Summary** (`booking-summary.tsx`, server): rows Court/Coverage/Date/Time and the off-peak and peak lines.
  - Compute the lines from the catalog rates plus `peak` rules (display only). The **total shown is `slot.price_centavos`** from fresh availability.
  - The Continue button is the form's submit (`form="details-form"` attribute) when selected, and disabled otherwise.
  - The hint copy follows the spec.
- Layout: `grid-cols-1 min-[900px]:grid-cols-[minmax(0,1fr)_340px]`. The aside is `hidden min-[900px]:block sticky top-[84px]`, and the bottom bar is `min-[900px]:hidden fixed`.
- `loading.tsx`: skeleton step cards.
- Existing tests in `app/book/__tests__` and `src/lib/booking/__tests__` must stay green. Update only assertions on removed markup (StepHeader), and say which ones.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Copy inline styles from the prototype. Styles go in stylesheet classes (CSP).
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.
- Change `params.ts`, `actions.ts` or the API client.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
pnpm --filter @cb/web lint && pnpm --filter @cb/web typecheck && pnpm --filter @cb/web test && pnpm --filter @cb/web build
git diff --quiet -- apps/web/src/lib
```
