---
type: prompt
plan: "[[2026-10-22-portfolio-ready]]"
id: 01
unit: U1
status: todo
model: sonnet
effort: medium
depends_on: []
parallel_group: A
files:
  create:
    - apps/web/app/opengraph-image.tsx
    - apps/web/app/__tests__/opengraph-image.test.tsx
  modify:
    - apps/web/app/layout.tsx
  delete: []
---
# 01 · Link-preview image

## Task
1. Create `apps/web/app/opengraph-image.tsx`: a static 1200×630 PNG link preview built with `next/og`'s
   `ImageResponse`.
2. In `apps/web/app/layout.tsx`'s `generateMetadata`, add `twitter: { card: "summary_large_image" },` after
   `openGraph`. Add nothing else to it (no twitter `title`, `description` or `images`: Next 16.4.2 copies those from
   `openGraph` when they're absent, in `next/dist/lib/metadata/metadata-resolution-primitives.js:393-422`). Change
   nothing else in that file.
3. Create `apps/web/app/__tests__/opengraph-image.test.tsx` to pin the exports and the render.

## Context
- Repo root: `/home/apa/Code/portfolio/court-booking-system`. pnpm + Turborepo; the web app is `apps/web` (`@cb/web`):
  Next.js 16 App Router, React 19, TypeScript, Tailwind 4, Vitest. `next/og` ships with `next`, so **add no
  dependency**.
- Kalaro Courts is a **fictional** venue and PayMongo runs in test mode only. Every preview must say so.
- **Review constraint: the build reads no env.** `next build` runs with no variables. This file must not import or
  call `getSiteUrl()` or `createEnv`, must not read `process.env`, and must not use `connection()`, `headers()`,
  `cookies()` or `fetch`. Use no custom font, because loading one would need a network fetch or a font file. The
  built-in font is **Geist Regular only** (`next/dist/compiled/@vercel/og/Geist-Regular.ttf`), so `fontWeight` has no
  effect: build hierarchy by size and colour. Beyond ASCII, use only `●`, `·`, `–` and `₱`. Those are checked to be
  in Geist; any other glyph makes `@vercel/og` fetch a fallback font from Google Fonts at build. With no dynamic API, Next prerenders the route at build (it shows as `○` in the
  build output). Next injects `og:image`, `og:image:width/height/type/alt` and `twitter:image` into every page's
  `<head>` automatically, as absolute URLs on `metadataBase`, which `layout.tsx` already sets per request from
  `SITE_URL`.
- No child route sets `openGraph` (they set only `title` and `robots`), so the root image applies site-wide.
- Content source: `apps/web/src/content/site.ts:6-12`:
  ```ts
  export const SITE = {
    name: "Kalaro Courts",
    tagline: "Book a court in under a minute.",
    description: "Basketball, volleyball, tennis, badminton and pickleball courts in one fictional Metro Manila complex, open daily 7 AM–11 PM.",
    testModeNotice: "Fictional venue · Test mode, no real payments",
  } as const;
  ```
  Import `SITE` from `@/content/site`. Importing the module is safe: it reads env only inside `getSiteUrl()`.
- Brand tokens (`apps/web/app/globals.css:4-8`): ink `#0f172a`, paper `#f8fafc`, court `#16a34a`, clay `#c2410c`,
  line `#cbd5e1`. The site's banner is ink on paper with a `●` mark (`src/components/test-mode-banner.tsx`).
- File shape (Next metadata file convention):
  ```tsx
  import { ImageResponse } from "next/og";
  import { SITE } from "@/content/site";

  export const alt = `${SITE.name}: ${SITE.tagline} ${SITE.testModeNotice}.`;
  export const size = { width: 1200, height: 630 };
  export const contentType = "image/png";

  export default function OpengraphImage() {
    return new ImageResponse(( /* layout */ ), { ...size });
  }
  ```
  Layout (Satori: flexbox only, inline `style`, every multi-child `div` needs `display: "flex"`): a paper background;
  a full-width ink strip at the top reading `● Fictional venue · Test mode, no real payments` (from
  `SITE.testModeNotice`) in paper; `SITE.name` large (about 104 px, ink); `SITE.tagline` below (about 40 px);
  a row of five sport labels (`Basketball`, `Volleyball`, `Tennis`, `Badminton`, `Pickleball`) as pills with a 2 px
  ink border; and a court-green bar along the bottom with `Open daily · 7 AM–11 PM · Metro Manila` in paper. Keep all
  text inside a 64 px margin. No images, emoji or external URLs.
- `layout.tsx:19-33` today:
  ```ts
  export async function generateMetadata(): Promise<Metadata> {
    await connection();
    return {
      metadataBase: new URL(getSiteUrl()),
      title: { default: title, template: `%s · ${SITE.name}` },
      description: SITE.description,
      openGraph: { type: "website", siteName: SITE.name, title, description: SITE.description, locale: "en_PH" },
    };
  }
  ```
  Add `twitter: { card: "summary_large_image", title, description: SITE.description },` after `openGraph`.
- Test pattern: `apps/web/app/__tests__/error.test.tsx` (Vitest, `describe`/`it`/`expect` from `vitest`, `@/` alias).
  `apps/web/vitest.config.ts` stubs `server-only` and maps tsconfig paths. Tests to write:
  1. `size` is `{ width: 1200, height: 630 }` and `contentType` is `"image/png"`.
  2. `alt` contains `SITE.name` and `SITE.testModeNotice`.
  3. The default export returns a `Response` whose body starts with the PNG signature
     (`[0x89, 0x50, 0x4e, 0x47]`). `ImageResponse` renders under plain Node 24 in `apps/web` (checked at audit), so
     this should work. If it can't render under Vitest (wasm/font loading), drop only this test, say so in your
     report, and rely on the build and container checks below.
- Formatting: Prettier (`pnpm format` fixes it); ESLint config from `@cb/config`.

## Do not
- Touch files outside the `files` list. If you must, stop and report why. In particular, don't change `proxy.ts`,
  `robots.ts`, `next.config.ts` or the Dockerfile.
- Add dependencies, fonts, `public/` assets, a `twitter-image` file or per-route images.
- Read env or the network in the image route.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
pnpm format:check && pnpm lint && pnpm typecheck
pnpm --filter @cb/web test
# static at build, with an empty environment
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build | grep -E '○ /opengraph-image'
# served by the standalone image
docker build -f apps/web/Dockerfile -t cb-web:local .
cid=$(docker run -d -p 18080:8080 -e SITE_URL=http://localhost:18080 cb-web:local); sleep 3
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://localhost:18080/opengraph-image   # 200 image/png
# head metadata: og:image, twitter:card=summary_large_image, twitter:image (autofilled). Without API_URL the
# page body shows the rates fallback; only the <head> matters here.
curl -s http://localhost:18080/ | grep -oE '<meta (property|name)="(og:image|twitter:card|twitter:image)"[^>]*>'
docker rm -f "$cid"
```
- Open `http://localhost:18080/opengraph-image` (or save the curl output to a scratch `.png` and view it): the notice
  strip, name, tagline, five sport pills and the green footer are all visible, and nothing is clipped.
