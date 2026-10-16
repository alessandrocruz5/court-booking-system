---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 14
unit: CBS-7
status: todo
model: opus
effort: high
depends_on: [13]
parallel_group: N
files:
  create:
    - apps/web/src/lib/api/env.ts
    - apps/web/src/lib/api/client.ts
    - apps/web/src/lib/api/schemas.ts
    - apps/web/src/lib/api/__tests__/schemas.test.ts
    - apps/web/src/lib/api/__tests__/client.test.ts
    - apps/web/src/test/server-only-stub.ts
  modify:
    - apps/web/package.json
    - apps/web/vitest.config.ts
    - apps/web/.env.example
    - pnpm-lock.yaml
  delete: []
---
# 14 · Web API client

## Task
Give the Next.js storefront a typed, **server-only** client for the Django storefront API. Every response is
validated with zod against schemas that mirror `docs/api/fixtures/*.json`, and the tests parse every fixture so the
two apps can't drift silently.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Web app: `apps/web` (`@cb/web`, Next.js 16.4,
  React 19, zod 4, vitest; `@cb/env` exports `createEnv(schema, source?)` and `baseEnvSchema`, and env is read **per
  call**, never at module top level, because `next build` runs with no env).
- **Read first**: `docs/api/README.md` and every file in `docs/api/fixtures/`. They're the contract.
  - Endpoints, each with header `Authorization: Bearer <INTERNAL_API_TOKEN>`:
    - `GET /api/v1/catalog`
    - `GET /api/v1/availability?date&sport&coverage&hours`
    - `POST /api/v1/bookings`
    - `POST /api/v1/checkout/confirm`
    - `POST /api/v1/checkout/release`
    - `POST /api/v1/bookings/lookup`
  - Errors are `{"error": code, "fields"?: string[]}` with statuses 400, 401, 404, 409, 413, 429 and 503.
- `pnpm --filter @cb/web add server-only`. zod is already a dependency.
- **`src/lib/api/env.ts`**: `apiEnvSchema = baseEnvSchema.extend({ API_URL: z.url(), INTERNAL_API_TOKEN: z.string().min(32) })`
  and `getApiEnv(source?)` using `createEnv`. API_URL is the backend origin, with no trailing slash.
- **`src/lib/api/schemas.ts`**: zod schemas and inferred types for `Catalog`, `Availability`, `BookingCreated`,
  `BookingSummary`, `CheckoutStatus`, `CheckoutRelease`, `BookingLookup` and `ApiErrorBody`. They must match the
  fixtures exactly. Use `z.enum` for sport, coverage, status and the checkout statuses. Prices are integer centavos.
- **`src/lib/api/client.ts`**: starts with `import "server-only";`.
  - `class ApiError extends Error` with `status: number` and `code: string` (from the body's `error`, or `"unavailable"`).
    Its message never includes the request body.
  - An internal `request<T>(path, schema, init)`:
    - Call `fetch(\`${API_URL}${path}\`)` with `cache: "no-store"`, `signal: AbortSignal.timeout(10_000)`, the bearer
      header, and `content-type: application/json` for POST.
    - A network failure or timeout → `ApiError(0, "unavailable")`.
    - A non-2xx response → parse it as `ApiErrorBody` → `ApiError(status, error)`.
    - A 2xx response → `schema.parse(json)`. A mismatch → `ApiError(502, "bad_response")`, logging the path only.
  - Typed functions: `getCatalog()`, `getAvailability({date, sport, coverage, hours})`,
    `createBooking(input & { clientIp })` (sent as `client_ip`), `confirmCheckout(checkoutSessionId)`,
    `releaseCheckout(checkoutSessionId)` and `lookupBooking({reference, email, clientIp})`. Use camelCase in
    TypeScript and snake_case on the wire, mapping explicitly.
  - `export function clientIpFrom(headers: Headers): string`. It returns the **rightmost** comma-separated entry of
    `x-forwarded-for`, trimmed. Cloud Run's front end appends the address it saw, so anything to the left of it is
    client-supplied. Fall back to `"0.0.0.0"`. Document this assumption.
- **`vitest.config.ts`**: add `resolve.alias` mapping `"server-only"` to `src/test/server-only-stub.ts` (an empty module),
  so tests can import the client. Keep the existing `oxc` JSX and `tsconfigPaths` settings.
- **`.env.example`**: add `API_URL=http://localhost:8000` and `INTERNAL_API_TOKEN=` (the same value as the backend's,
  server only, **never `NEXT_PUBLIC_`**), with fun-run-style comments.
- **Tests**:
  - `schemas.test.ts`: read **every** `*.json` in `../../../../../../docs/api/fixtures` (resolve from the repo root with
    `fileURLToPath(new URL(…, import.meta.url))`) and parse each with its schema. Map file names to schemas
    explicitly. An unmapped fixture fails the test, so new fixtures can't be skipped.
  - `client.test.ts` (mock `fetch` with `vi.stubGlobal`):
    - Sends the bearer token, `no-store` and the snake_case body.
    - A 409 `slot_taken` becomes `ApiError(409, "slot_taken")`.
    - A malformed 200 becomes `bad_response`.
    - A rejected fetch becomes `unavailable`.
    - `clientIpFrom("1.1.1.1, 2.2.2.2")` is `"2.2.2.2"`.
    - With `INTERNAL_API_TOKEN` unset, `getCatalog` throws without calling `fetch`.
- Review constraints:
  - **Internal API**: the token never reaches a client component, and nothing is `NEXT_PUBLIC_`.
  - **The build reads no env.**
  - **No caching of API responses.**

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Call the API from any client component, or add pages. Prompts 15–17 add pages.
- Add a fetch wrapper library.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
pnpm install --frozen-lockfile
pnpm format:check && pnpm lint && pnpm typecheck
pnpm --filter @cb/web test
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build
```
