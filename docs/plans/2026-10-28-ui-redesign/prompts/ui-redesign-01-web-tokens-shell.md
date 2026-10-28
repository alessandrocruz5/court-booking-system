---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 01
unit: U1
status: todo
model: sonnet
effort: medium
depends_on: []
parallel_group: A
files:
  create:
    - apps/web/src/content/sports.ts
    - apps/web/src/content/__tests__/sports.test.ts
  modify:
    - apps/web/app/globals.css
    - apps/web/app/layout.tsx
    - apps/web/src/components/test-mode-banner.tsx
  delete: []
---
# 01 · Web tokens, sport colours and the shell

## Task
1. Extend the Tailwind `@theme` in `globals.css` with the spec's tokens.
2. Add sport colours in `src/content/sports.ts`.
3. Restyle the banner, header and footer.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. Web: `apps/web` (Next.js, Tailwind v4 `@theme`).
- Spec: `docs/plans/2026-10-28-ui-redesign/design-spec.md`, and the prototype `docs/plans/2026-10-28-ui-redesign/prototypes/Kalaro Booking.dc.html` (header, banner, footer).
- `globals.css` today defines `ink/paper/court/clay/line` and the classes `.disp .wrap .eyebrow .row .banner .btn .btn-accent`.
  - Keep those class names working: other pages use them until 02–04 land.
  - Add these colours: `ink-2 #1e293b`, `ink-3 #334155`, `slate-6 #475569`, `slate-5 #64748b`, `slate-4 #94a3b8`, `line-soft #e2e8f0`, `hair #f1f5f9`, `court-dark #15803d`, `court-soft #dcfce7`, `court-tint #f0fdf4`, `court-ink #14532d`, `clay-light #fb923c`, `warn-bg #fff7ed`, `warn-line #fed7aa`, `warn-ink #9a3412`, `pending #ea580c`.
  - Add `--font-mono` for JetBrains Mono.
  - Update `.wrap` to `max-width: 1120px; padding-inline: 20px`.
  - Update `.btn` and `.btn-accent` to the spec (radius 10, `1.5px` outline border).
  - Add `.btn-dark`.
  - Add a focus ring: `outline: 3px solid #16a34a55; outline-offset: 1px`.
- `layout.tsx`: load `JetBrains_Mono` from `next/font/google` (weights 500 and 700, `variable: "--font-jetbrains"`) next to Archivo. Set the body font to Archivo, not the system stack.
  - Header: sticky, white, logo mark plus wordmark linking to `/`, with "Find booking" → `/booking` and "Book" → `/book`.
  - Footer: two spans, as in the spec.
- `test-mode-banner.tsx`: add the 7px `#4ade80` dot (`aria-hidden`). The text stays `SITE.testModeNotice` exactly.
- `src/content/sports.ts`: `export const SPORT_COLORS = { basketball: "#e0662d", volleyball: "#d4a017", tennis: "#5b9a1e", badminton: "#2b7fc4", pickleball: "#14958a" } as const`.
  - Its test asserts the key set equals the `sports[].id` set in `docs/api/fixtures/catalog.json`, following `site.test.ts`'s fixture read.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
pnpm --filter @cb/web lint && pnpm --filter @cb/web typecheck && pnpm --filter @cb/web test
pnpm --filter @cb/web build
```
- Every page still renders "Fictional venue · Test mode, no real payments" (the existing tests pass).
