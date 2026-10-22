---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 03
unit: CBS-2
status: done
model: sonnet
effort: medium
depends_on: [01]
parallel_group: C
files:
  create:
    - apps/web/package.json
    - apps/web/next.config.ts
    - apps/web/tsconfig.json
    - apps/web/eslint.config.js
    - apps/web/postcss.config.mjs
    - apps/web/vitest.config.ts
    - apps/web/.env.example
    - apps/web/proxy.ts
    - apps/web/app/layout.tsx
    - apps/web/app/page.tsx
    - apps/web/app/globals.css
    - apps/web/app/error.tsx
    - apps/web/app/global-error.tsx
    - apps/web/app/not-found.tsx
    - apps/web/app/robots.ts
    - apps/web/app/icon.svg
    - apps/web/app/api/health/route.ts
    - apps/web/app/__tests__/error.test.tsx
    - apps/web/public/.gitkeep
    - apps/web/src/content/site.ts
    - apps/web/src/components/test-mode-banner.tsx
    - apps/web/src/lib/csp.ts
    - apps/web/src/lib/__tests__/csp.test.ts
  modify:
    - pnpm-lock.yaml
  delete: []
---
# 03 · Next.js storefront skeleton

## Task
Create `apps/web` (`@cb/web`), the customer-facing Next.js 16 storefront shell. It needs a test-mode banner on every
page, a per-request CSP nonce, static security headers, safe error screens, a health route, and **standalone output**
for Cloud Run. Copy the proven shell from fun-run and adapt it.

## Context
- Repo root: `/Users/alessandrocruz/Code/portfolio/court-booking-system`. Prompt 01 created the root and `@cb/config` and `@cb/env`.
- Reference, **read only**: `/Users/alessandrocruz/Code/fun-run-website/apps/web`. Copy and adapt:
  - `package.json`: name `@cb/web`, scripts `dev` (`next dev --port 3000`), `build`, `start`, `lint`, `typecheck`, `test`.
    Dependencies `@cb/env: workspace:*`, `next`, `react`, `react-dom` and `zod` at fun-run's ranges. **Drop** `@rr/db`,
    `@rr/email`, `@rr/payments` and `@rr/ui`. The devDependencies are the same, with `@cb/config`.
  - `tsconfig.json`, `eslint.config.js`, `postcss.config.mjs` and `vitest.config.ts`: as is, with `@rr` → `@cb`.
  - `next.config.ts`: keep the `headers()` block (`/api/:path*` set to `no-store`; nosniff,
    `Referrer-Policy: strict-origin-when-cross-origin` and `Permissions-Policy` on `/:path*`). Add
    `output: "standalone"`, `outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url))` (the monorepo
    root, so the standalone server traces workspace packages), `poweredByHeader: false` and
    `transpilePackages: ["@cb/env"]`.
  - `proxy.ts` (Next 16 renamed middleware to proxy): copy it. Replace `upgradeInsecure: process.env.VERCEL_ENV === "production"`
    with `upgradeInsecure: Boolean(process.env.K_SERVICE)`, since Cloud Run sets `K_SERVICE` and `next start` on
    localhost doesn't. Keep the matcher.
  - `src/lib/csp.ts` and its test (`fun-run-website/apps/web/src/lib/__tests__/csp.test.ts`): remove every Turnstile
    origin. There are no third-party origins at all, because PayMongo is reached by a top-level redirect, not a frame
    or script. Keep "no `form-action`", because the booking action redirects to `checkout.paymongo.com`. Update the
    tests to match.
  - `app/error.tsx`, `app/global-error.tsx`, `app/not-found.tsx` and `app/__tests__/error.test.tsx`. Next 16.4 passes
    `{ error, retry }`. Only `error.digest` is shown, as "Reference: …"; the message and stack are never rendered.
    `global-error` brings its own `<html>`, the banner and a plain `<a href="/">` exit that works without JS.
    fun-run's versions import `Button` and `ButtonLink` from `@rr/ui`, which this app doesn't have: use a plain
    `<button type="button">` and `next/link`'s `<Link>`, styled by `.btn` and `.btn-accent` in `app/globals.css`.
  - `app/api/health/route.ts`: as is (liveness only, no backend call).
- **Read `node_modules/next/dist/docs/` before writing Next-specific code** (resolve `next` from `apps/web`). This
  Next version has breaking changes from older releases.
- New content:
  - `src/content/site.ts` exports `SITE = { name: "Kalaro Courts", tagline: "Book a court in under a minute.",
    description: "Basketball, volleyball, tennis, badminton and pickleball courts in one fictional Metro Manila
    complex, open daily 7 AM–11 PM.", testModeNotice: "Fictional venue · Test mode, no real payments" }` and
    `getSiteUrl()`, which reads `SITE_URL` through `createEnv` **per call** (copy the pattern from
    `fun-run-website/apps/web/src/content/site.ts`, `getSiteUrl` only). Kalaro Courts is fictional.
  - `src/components/test-mode-banner.tsx`: copy fun-run's, reading `SITE.testModeNotice`.
  - `app/layout.tsx`: banner, then a simple header (wordmark linking to `/`), `{children}`, then a footer line. Use
    `generateMetadata()` with `await connection()` before reading `SITE_URL` (fun-run's `layout.tsx:27-43` pattern),
    so the build reads no env. Use one Google font via `next/font/google` (a sporty grotesk for display, system
    stack for body), or none.
  - `app/globals.css`: Tailwind v4 (`@import "tailwindcss"`) and design tokens as CSS variables under `@theme`:
    `--color-ink` (#0f172a), `--color-paper` (#f8fafc), `--color-court` (#16a34a, a court-green accent),
    `--color-clay` (#c2410c, peak-hour accent), `--color-line` (#cbd5e1), plus `.banner`, `.btn` and `.btn-accent` styles.
  - `app/page.tsx`: a placeholder hero (venue name, tagline, "Book a court" link to `/book`). Prompt 17 builds the real
    landing page.
  - `app/robots.ts` allows all except `/book`, `/booking` and `/staff` (each crawl of those wakes the backend and
    Neon), and reads `getSiteUrl()` per request. `app/icon.svg` is a simple court glyph.
    `public/.gitkeep` is there so the Dockerfile's `COPY public` never fails.
  - `.env.example`: `SITE_URL=http://localhost:3000`, commented ("public origin, no trailing slash, read per request").
    Prompts 14 and 17 add more keys.
- Review constraints that apply: **the build reads no env** (nothing reads `process.env` at module top level in code
  `next build` evaluates). **Every page shows the test-mode banner**, including 404 and global-error. **API responses
  are `no-store`.**

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies beyond fun-run's web set minus the dropped workspace packages.
- Add booking pages, API calls or Turnstile.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/portfolio/court-booking-system
pnpm install --frozen-lockfile
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build          # builds with no env
ls apps/web/.next/standalone/apps/web/server.js                      # standalone output in monorepo layout
```
- `SITE_URL=http://localhost:3000 pnpm --filter @cb/web start`. Then `curl -s localhost:3000/ | grep -c "Fictional venue · Test mode"` is ≥ 1,
  `curl -sI localhost:3000/ | grep -i content-security-policy` shows a nonce, and `curl -s localhost:3000/api/health`
  returns `{"status":"ok"}`. A missing page (404) also shows the banner.
- If `next dev` generates `apps/web/AGENTS.md`, leave it untracked and mention it in your report.
