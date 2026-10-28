---
type: audit
plan: "[[2026-10-22-portfolio-ready]]"
---
# Audit: portfolio-ready

## Audit 2026-10-22: PASS-WITH-CHANGES
Graph built: none (grep only) · Symbols traversed: 9 (`generateMetadata`, the `opengraph-image` route, `ImageResponse`, `proxy` matcher, `robots`, `SITE`, `SITE_URL` wiring, README links, the O4 branches) · Missed blast-radius items: 3

User answers recorded with this audit: Sprint 2's Epic is **CBS-11**; the README gets **no Author section**.

| Sev | Check | Finding | Evidence | Fix |
|---|---|---|---|---|
| FIX | Usability | O3 saves the screenshots straight into `docs/images/` on `main`, before U2's branch exists. They're untracked non-bookkeeping files, so build-unit's clean-tree gate stops or asks. | `~/.claude/skills/build-unit/SKILL.md:38` ("must be clean, or the user must accept"), `:137` | O3 saves to `~/Pictures/kalaro-courts/` instead. Prompt 02 step 1: `mkdir -p docs/images && cp ~/Pictures/kalaro-courts/{…}.png docs/images/` (a byte copy, no re-encode). Reword "you don't create the PNGs". |
| FIX | Usability | The plan (Blast radius row "`format:check`") and prompt 02 claim `pnpm format:check` runs Prettier on Markdown. It doesn't: it checks only TS/JS/JSON, so README formatting goes unverified. | `package.json:15` `prettier --check "**/*.{ts,tsx,js,mjs,cjs,json}"` | Correct the row and the prompt. Add `pnpm exec prettier --check README.md` to 02's Done-when (root devDependency; config `@cb/config/prettier`). |
| FIX | Usability | The README link check prints `MISSING …` but exits 0, so it can't fail a gate. `grep -c 'docs/images/'` counts lines, not images: a 2×2 table puts two on one line. | Plan E2E and prompt 02 Done-when | Use `! ( grep -oE '\]\(([^)#]+)' README.md \| sed 's/](//' \| grep -v '^http' \| while read -r p; do test -e "$p" \|\| echo "MISSING $p"; done ) \| grep MISSING` and `test "$(grep -oE 'docs/images/[a-z-]+\.png' README.md \| sort -u \| wc -l)" -eq 4`. |
| FIX | Bloat | Prompt 01 adds `twitter: { card, title, description }`, but the plan's Decision says `{ card }` only. Next 16.4.2 already fills twitter `title`, `description` and `images` from `openGraph` when they're absent, so the extra keys are redundant. They also freeze the twitter title against future openGraph edits. | `node_modules/next/dist/lib/metadata/metadata-resolution-primitives.js:393-422` (`postProcessMetadata`: `if (!hasTwImages) autoFillProps.images = openGraph.images`); `next` 16.4.2 | Prompt 01: `twitter: { card: "summary_large_image" }` only. Add a Done-when grep for `twitter:image`, which proves the autofill. |
| FIX | Notes & constraints | The Open questions are now answered (CBS-11; no author), but prompt 02 still carries the conditional Author section, and O1 still says "see Open questions". | Prompt 02 Context item 9; plan `## Open questions` | 02: "No Author section." O1: `Epic: CBS-11`. Move both answers to Decisions and delete Open questions. |
| NOTE | Usability | `ImageResponse`'s only bundled font is Geist Regular, so `fontWeight: bold` renders regular. Every glyph the image uses (`● · – ₱`) is in that font, so no Google Fonts fetch happens at build (that only triggers for missing glyphs). | `next/dist/compiled/@vercel/og/Geist-Regular.ttf`; fonttools cmap check: all 4 → True; `index.node.js:20367` (the fonts.googleapis fallback) | Prompt 01: build hierarchy by size, not weight. Use only those glyphs beyond ASCII. |
| NOTE | Usability | The PNG-signature test is viable: `ImageResponse` renders under plain Node 24 in `apps/web`. | `node -e "import('next/og.js')…"` → `image/png [137, 80, 78, 71]` | Keep the test and its fallback clause. |
| NOTE | Unit shape | Every merge to `main` deploys both services, including docs-only U2 (CI push → Deploy `workflow_run`). | `.github/workflows/ci.yml:3-6`; `deploy.yml` `workflow_run` | Accept. The Artifact Registry cleanup policy bounds storage. |
| NOTE | Notes & constraints | O1's new Sprint headings drop the existing `(planned …)` dates. The untracked hotfix line has no key, unlike the §8 format. | `TASKS.md:6`, `:96` | Keep the planned date: `## Sprint 1 — Court booking MVP   (planned 2026-10-16) · v0.1.0 (2026-10-21)`. Accept the keyless hotfix line; it's marked `(untracked)`. |
| NOTE | Usability | R2's check "`TASKS.md` has no `[~]`" fails while Sprint 3 units are in flight. | Plan End-to-end, R2 bullet | Scope it to the Sprint 1 and 2 blocks. |
| NOTE | Breakage | O4 is safe: every `CBS-*` branch and `develop` is merged into `main`; only the Dependabot remotes aren't. | `git branch --no-merged main` → empty; `git branch -r --no-merged origin/main` → 3 dependabot refs | None. |

Verified non-findings: `og:image` will be absolute on the live origin, because Cloud Run sets `SITE_URL=$WEB_URL`
(`deploy.yml:128`). No child route sets `openGraph` (grep), so the root image applies everywhere. `robots.ts` doesn't
disallow `/opengraph-image`. The README highlight claims match the code: `payments/confirm.py:119,133` (livemode),
`payments/env.py:11` (`sk_test_`), `storefront/views.py:43,244,381` (Postgres rate limits), `payments/confirm.py:158`
(reacquire), the `USER` lines in both Dockerfiles (non-root). No env key, API contract, migration or high-stakes path
is touched.

**Bloat estimate:** planned 3 code files / ~90 LOC, plus the README (~200 lines) and 4 PNGs; minimal viable is the same.
**Model cost:** 01 sonnet and 02 sonnet are right; haiku is too risky for the Satori layout and for the README prose,
which is the portfolio's face.
