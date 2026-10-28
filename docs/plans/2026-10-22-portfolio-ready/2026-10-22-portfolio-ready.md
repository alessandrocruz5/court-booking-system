---
type: plan
kind: feature
status: audited
repo: court-booking-system
delivery: pr
base: main
sprint: 3
epic:
created: 2026-10-22
risk: low
prompts: 2
graph_built: none
tags: [plan]
---
# Portfolio ready: close out, verify production, showcase

## Request
> what else do i need to do to consider this complete and portfolio ready

The code is done. Sprint 1 (CBS-2…CBS-10) and Sprint 2 (CBS-12…CBS-16) are merged and released (PR #18). The last
Deploy run (2026-10-22 03:57Z) is green. On 2026-10-22, `$WEB_URL/`, `/book`, `/privacy` and
`$BACKEND_URL/dashboard/login/` all answered 200 with the test-mode banner. What's missing is proof that production
works end to end, a ledger that matches reality, and a repo page that sells the work.

| # | Requirement |
|---|---|
| R1 | Production is verified against all 13 items of the runbook's `## Pre-release checklist` on Cloud Run, and the sign-off is recorded in this plan's Log. |
| R2 | The ledger matches reality: CBS-16 is `[x]`, Sprints 1 and 2 have versions, `CHANGELOG.md` exists, both earlier plans are `done`, and the post-release direct commits on `main` are recorded. |
| R3 | From the README alone, a visitor to the GitHub repo can see what the project is, open a working live demo, see screenshots, follow a demo script with real links, and read the engineering decisions and the known limits. |
| R4 | Sharing `$WEB_URL` (LinkedIn, Slack, Messenger, X) shows a 1200×630 preview image that names the venue fictional and the payments test mode. |
| R5 | The repo is tidy: merged branches and `develop` are deleted, the 3 open Dependabot PRs are resolved, and the GitHub "About" has a homepage and topics. |

## Context used
- `TASKS.md`: CBS-16 still `[~]`; Sprint 2 `Epic: (key not recorded)`, `Branch base: develop`. CBS-10's Release line says to run the pre-release checklist on Cloud Run "before calling the MVP done". No line records that it was run.
- `docs/plans/_index.md`: both plans are still `in-progress`. Their Logs end at the CBS-10 merge and the CBS-16 merge; neither logs a checklist run.
- `docs/runbook.md:604-643` `## Pre-release checklist` (13 unchecked items); `:505` `## Staff dashboard` "Check it" steps.
- `README.md`: "Demo in 3 minutes" uses `$WEB_URL` placeholders, with no live link, screenshots, badges or highlights section.
- No `CHANGELOG.md` at the root. Template: `~/.claude/skills/plan-feature/templates/CHANGELOG.md`.
- Git: `origin/main` is 4 commits ahead of `origin/develop` (ca163c8 "Deploy fixes", e6dc9a1 "Health endpoint fixes", c28abdb "Path changes and variable changes", plus the merge). They were pushed directly to `main`, outside the ledger. Merged branches CBS-3…CBS-16 still exist locally and on `origin`.
- `gh pr list`: open Dependabot PRs #3 (node 24→26-slim, web Dockerfile), #4 (typescript 6→7), #5 (@types/node 24→26). `gh repo view`: public, `homepage: null`, `topics: []`.
- `gh variable get WEB_URL`/`BACKEND_URL`: `https://cb-web-6699055361.asia-southeast1.run.app`, `https://cb-backend-6699055361.asia-southeast1.run.app` (public Cloud Run URLs, not secrets).
- Live check (2026-10-22): the first `$WEB_URL/` request took 8.6 s (cold start of `cb-web`, then `cb-backend` for the streamed rates); later pages took 0.3–0.5 s. Free tier: min instances 0, no keep-warm (review constraint).
- `apps/web/app/layout.tsx:19-33`: `generateMetadata` sets `openGraph` without `images`, and there's no `twitter` field. The live `<head>` has no `og:image`. No child route sets `openGraph` (grep), so a root `opengraph-image` applies to every page.
- `apps/web/proxy.ts:27-37`: the matcher covers every non-`api/`, non-static path, so `/opengraph-image` also gets the CSP header (harmless on an image). `apps/web/app/robots.ts`: disallows only `/book`, `/booking` and `/staff`, so crawlers can fetch the image.
- `apps/web/next.config.ts:6`: `output: "standalone"`; `apps/web/Dockerfile:33-43`: `PORT=8080`, `node apps/web/server.js`.
- `apps/web/app/__tests__/error.test.tsx`: the test pattern (vitest, `renderToStaticMarkup`, `vi.mock("../globals.css")`). `apps/web/vitest.config.ts`: `server-only` stub, tsconfig paths.
- `apps/web/src/content/site.ts:6-12`: `SITE.name`, `SITE.tagline`, `SITE.description`, `SITE.testModeNotice`.
- Highlight sources checked to exist: `bookings/models.py` (`SlotLock` `UniqueConstraint`, :127), `bookings/holds.py`, `payments/confirm.py:114` (`confirm_payment`; amount check :135), `payments/webhook.py`, `core/migrations/0002_app_role.py`, `bookings/management/commands/nightly.py`, `dashboard/queries.py`, `storefront/auth.py`, `apps/web/src/lib/csp.ts`, `apps/web/src/lib/booking/checkout-cookie.ts`, `config/env.py`. No `send_mail`/`EMAIL_BACKEND` in backend code: the app sends no email.
- `CLAUDE.md` `## Review constraints` (test-mode banner, personal data, free tier, scope), `## Workflow` (`Base branch: main`).
- Graph: none (`graphify-out/` is absent). Blast radius came from grep.

## Options
| Option | Cost | Time | Risk | Maintenance | Compliance |
|---|---|---|---|---|---|
| A. Close out and showcase: the checklist, the ledger, the README, an OG image, repo hygiene | 2 sonnet prompts plus user ops | ~1 day | Low; no high-stakes paths | None | Screenshots must hold no real personal data |
| B. A, plus a Playwright E2E smoke test in CI | +1 opus prompt | +2–3 days | Medium; touches `.github/workflows/**` (high-stakes), and CI can't finish a PayMongo hosted checkout | A browser suite to keep green | None |
| C. A, plus clearing the deferred backlog (SlotLock index migration, legacy cookie removal, digest pins, Dependabot majors) | +3–4 prompts, opus | +2 days | Medium; a migration and Dockerfiles | Lower long-term | None |

**Recommendation:** A. A reviewer judges the README, the live demo and the link preview. B and C are mostly invisible
to them, and they become talking points in the README's "Known limits" instead. **Chosen:** A (user, 2026-10-22).

## Decisions
- **Scope A** (user, 2026-10-22).
- **Base branch `main`** (user, 2026-10-22). It matches `CLAUDE.md` `## Workflow`. `develop` holds nothing that
  `main` lacks (0 commits ahead), so it's deleted in O4. Every unit merge deploys.
- **Screenshots are taken by the user** from the shot list in O3 (user, 2026-10-22). The dashboard needs the
  demo-button sign-in (CSRF POST), so a script would cost more than it saves. They're saved **outside the repo**
  (`~/Pictures/kalaro-courts/`), and prompt 02 copies them in byte for byte, so `main` stays clean for build-unit's
  gate (audit 2026-10-22).
- **Sprint 2's Epic is CBS-11; the README has no Author section** (user, 2026-10-22).
- **Screenshots show only demo or masked data.** Dashboard shots are taken signed in as the demo **viewer** (masking
  happens in `dashboard/queries.py`). No shot shows a real name, email or mobile, including the user's own
  checklist bookings. This follows from RA 10173: a public repo is a disclosure.
- **The link-preview image is generated in code** (`app/opengraph-image.tsx`, `next/og` `ImageResponse`, no network
  font fetch). It's prerendered at build and reads no env, which keeps the "build reads no env" constraint. It
  carries `SITE.testModeNotice`, so a preview never looks like a real business. `layout.tsx` adds only
  `twitter: { card: "summary_large_image" }`, so X and Slack use the large card. Next 16.4.2 fills `og:image` from the
  file convention and copies twitter `title`, `description` and `images` from `openGraph`
  (`metadata-resolution-primitives.js:393-422`; audit 2026-10-22). The bundled font is Geist Regular only, and it covers
  `● · – ₱`, so the image builds hierarchy by size, not weight, and never triggers the Google Fonts fallback.
- **Cold start is documented, not fixed.** The README says the first load can take about 10 s because both services
  scale to zero. Keep-warm pings are forbidden by the free-tier constraint.
- **The live URLs go in the README** as plain links. They're public `run.app` URLs; the project number in them is not
  a secret.
- **Bookkeeping (O1) is not a unit.** Per workflow §8, it's committed on `main` as `Sprint 1–2 wrap up`. Versions:
  Sprint 1 → `0.1.0` (2026-10-21), Sprint 2 → `0.2.0` (2026-10-21), and the three post-release direct commits →
  `0.2.1` (2026-10-22, hotfix, untracked: no ticket). Sprint 3 → `0.3.0` when U1 and U2 merge.
- **Order:** O1 → U1 (anytime) → O2 → O3 → U2 → O4. U2's README claims a verified demo, so it waits for the O2
  sign-off and the O3 images.

**Non-goals:** browser E2E tests; Lighthouse CI; the SlotLock `starts_at` index; removing the legacy `cb_checkout`
format (the CBS-16 should-fix; legacy entries have aged out since the 2026-10-21 deploy); digest-pinned base images;
Dependabot major upgrades (TS 7, Node 26); a custom domain; keep-warm or min-instances > 0; a case-study blog post;
changes to `docs/runbook.md` (O2 records results in this plan's Log, not by ticking the runbook's template).

## Change list
| File | Action | Why | Req | Prompt |
|---|---|---|---|---|
| `apps/web/app/opengraph-image.tsx` | C | 1200×630 PNG preview with name, tagline, sports and the test-mode notice; static, no env | R4 | 01 |
| `apps/web/app/__tests__/opengraph-image.test.tsx` | C | Pins size, content type and alt (with the test-mode notice), and that it renders a PNG | R4 | 01 |
| `apps/web/app/layout.tsx` | M | `twitter: { card: "summary_large_image" }` in `generateMetadata` | R4 | 01 |
| `README.md` | M | Showcase: badges, live demo, screenshots, highlights, real links in the demo script, known limits | R3 | 02 |
| `docs/images/storefront-home.png` | C (copied) | Screenshot from O3, copied in from `~/Pictures/kalaro-courts/` | R3 | 02 |
| `docs/images/book-slots.png` | C (copied) | Screenshot from O3 | R3 | 02 |
| `docs/images/dashboard-overview.png` | C (copied) | Screenshot from O3 | R3 | 02 |
| `docs/images/dashboard-schedule.png` | C (copied) | Screenshot from O3 | R3 | 02 |
| `TASKS.md`, `CHANGELOG.md`, `docs/plans/**` | M/C | Bookkeeping (O1), not in any unit PR | R2 | — |

## Blast radius
**Risk:** low. No high-stakes path is touched. `layout.tsx` is shared by every page, but the change only adds one
metadata field.

| Affected | Kind | Via | Breaks? | Mitigation |
|---|---|---|---|---|
| Every web page's `<head>` | Direct | `layout.tsx` `generateMetadata` | No. It adds `twitter:card`; `og:image` and `twitter:image` are injected by the file convention. No test asserts the metadata (grep). | Done-when greps the built HTML for `og:image` |
| Child routes' `metadata` (`book`, `booking`, `privacy`, `book/success`, `book/cancelled`) | Direct | Next metadata merge | No. They set only `title`/`robots`, never `openGraph`, so the root image applies. | — |
| `next build` with no env | Non-graph | Review constraint "build reads no env" | It would break if the image read `getSiteUrl()` or fetched a font. | Prompt forbids env and network; Done-when runs `pnpm build` with an empty env and checks the route is static (`○`) |
| Standalone Docker image | Non-graph | `output: "standalone"` tracing of `next/og`'s wasm/fonts | It could 500 at runtime if not traced. | Done-when builds the image and curls `/opengraph-image` from the container |
| `proxy.ts` CSP matcher | Non-graph | `/opengraph-image` matches | No. The CSP header on a PNG is ignored. | — |
| `robots.ts` | Non-graph | crawler access | No. `/opengraph-image` isn't disallowed. | — |
| Test-mode banner constraint | Review constraint | the image is not a page | No, and the image carries the notice anyway. | Test asserts `alt` contains `SITE.testModeNotice` |
| `format:check` | Non-graph | It checks only `**/*.{ts,tsx,js,mjs,cjs,json}` (`package.json:15`), so not `README.md` | No; the README's formatting would simply go unchecked. | 02's Done-when runs `pnpm exec prettier --check README.md` (audit 2026-10-22) |
| build-unit clean-tree gate | Non-graph | untracked screenshots on `main` | It would stop U2 if the PNGs were saved into the repo first. | O3 saves outside the repo; 02 copies them in (audit 2026-10-22) |
| gitleaks (CI `secrets`) | Non-graph | README text | No secrets added; the test card number is public PayMongo test data, already in the README. | — |
| Personal data | Review constraint | screenshots in a public repo | Yes, if a shot shows a real booking. | O3: viewer session only; U2 Done-when asks the user to confirm |

**Known risks in the touched area:** cold starts (8.6 s first hit, measured) are a first-impression risk for a
portfolio link. They're mitigated by a README note, because keep-warm is forbidden. The RA 10173 exposure through
screenshots is handled above.

## Units
| Unit | Title | Category | Prompts | Depends | High-stakes | Acceptance criteria |
|---|---|---|---|---|---|---|
| U1 | Link-preview image | Added | 01 | — | no | R4: `$WEB_URL/` `<head>` has `og:image` (absolute, on `SITE_URL`) and `twitter:card=summary_large_image`; `$WEB_URL/opengraph-image` returns a 1200×630 `image/png` showing the test-mode notice; `next build` lists it as static. |
| U2 | Showcase README | Changed | 02 | U1, O2, O3 | no | R3: the README has CI and license badges, live links to the storefront and dashboard with a cold-start note, 4 screenshots from `docs/images/`, a demo script with real links, an "Engineering highlights" section linking real files, and a "Known limits" section; every relative link resolves; `pnpm format:check` passes. |

## Ops steps (user, not units)
**O1 · Close Sprints 1–2 (now, on `main`)**. This is bookkeeping, so Claude can do it when you ask.
- `TASKS.md`: CBS-16 `[~]` → `[x]`. Sprint 2 gets `Epic: CBS-11`, and its `Branch base` stays `develop`
  (historical). Tag the headings, keeping the planned dates:
  `## Sprint 1 — Court booking MVP   (planned 2026-10-16) · v0.1.0 (2026-10-21)` and
  `## Sprint 2 — Follow-up fixes   (planned 2026-10-21) · v0.2.0 (2026-10-21)`. Add `## Hotfixes` with
  `- [x] (untracked) — Deploy, health endpoint and path fixes · Fixed · direct to main: ca163c8, e6dc9a1, c28abdb · v0.2.1 (2026-10-22)`.
- `CHANGELOG.md` (new, from the template): `0.2.1`, `0.2.0`, `0.1.0`, each unit under its category, using the TASKS
  Story lines.
- Both earlier plans: frontmatter `status: done`, a Log line `2026-10-22: done (released; checklist in
  [[2026-10-22-portfolio-ready]])`, and `_index.md` rows `done`.
- Commit `Sprint 1–2 wrap up` on `main` and push (no unit PR carries it).

**O2 · Pre-release checklist on Cloud Run (after U1 deploys, before U2)**
- Run all 13 items of `docs/runbook.md#pre-release-checklist`, in order, against the live URLs. Item 9 needs a second
  network (phone hotspot). Item 13 needs the browser console open.
- Record one Log line per item here: pass, or fail plus the symptom. Don't tick the runbook; it's a reusable
  template.
- Any fail: stop and run `/plan-feature hotfix <symptom>`. U2 waits.
- Also check the U1 preview: paste `$WEB_URL` into https://www.opengraph.xyz/ (or a LinkedIn post draft) and confirm
  the image and the notice show.

**O3 · Screenshots (after O2)**: viewport 1440×900, browser zoom 100%, light mode, PNG, each ≤ 500 KB (use `oxipng` or
`pngquant` if needed), saved **outside the repo** to `~/Pictures/kalaro-courts/` (prompt 02 copies them in):

| File | Where | State |
|---|---|---|
| `storefront-home.png` | `$WEB_URL/` | Hero and "Sports & rates", with the banner visible |
| `book-slots.png` | `$WEB_URL/book` → Basketball → Half court → 2 h → tomorrow | Slot grid with an evening (peak) slot picked and its price |
| `dashboard-overview.png` | `$BACKEND_URL/dashboard/` via **Explore the owner demo** (VIEWER) | KPIs, revenue by sport, heatmap |
| `dashboard-schedule.png` | Schedule, today, VIEWER | The grid with walk-ins and a block; names masked |

No shot may show an unmasked real name, email or mobile. Don't screenshot `/book/success` with your own booking.

**O4 · Repo hygiene (after U2 merges)**
```sh
# merged unit branches and develop (develop is 0 ahead of main)
git branch -d CBS-3 CBS-4 CBS-5 CBS-6 CBS-7 CBS-8 CBS-9 CBS-10 CBS-12 CBS-13 CBS-14 CBS-15 CBS-16 develop
git push origin --delete CBS-3 CBS-4 CBS-5 CBS-6 CBS-7 CBS-8 CBS-9 CBS-10 CBS-12 CBS-13 CBS-14 CBS-15 CBS-16 develop
# Dependabot majors: decline for the finished demo (re-open later if you upgrade)
gh pr comment 3 --body "@dependabot ignore this major version"   # node 26-slim
gh pr comment 4 --body "@dependabot ignore this major version"   # typescript 7
gh pr comment 5 --body "@dependabot ignore this major version"   # @types/node 26 (runtime is Node 24)
# GitHub "About"
gh repo edit --homepage "$(gh variable get WEB_URL)" \
  --add-topic nextjs --add-topic django --add-topic htmx --add-topic postgresql --add-topic neon \
  --add-topic cloud-run --add-topic paymongo --add-topic turborepo --add-topic booking-system --add-topic portfolio
```
Then pin the repo on your GitHub profile. Once O4 is done, Sprint 3's roll-up tags `0.3.0`.

## Prompts
| # | Title | Unit | Model | Effort | Depends | Group | Files |
|---|---|---|---|---|---|---|---|
| 01 | Link-preview image | U1 | sonnet | medium | — | A | `apps/web/app/opengraph-image.tsx`, `apps/web/app/__tests__/opengraph-image.test.tsx`, `apps/web/app/layout.tsx` |
| 02 | Showcase README | U2 | sonnet | medium | 01 | B | `README.md`, `docs/images/*.png` (user-provided) |

No opus prompts: no high-stakes paths, no payments, auth or migrations.

## End-to-end verification
```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
docker compose up -d --wait db
pnpm test
pnpm build
docker build -f apps/web/Dockerfile -t cb-web:local .
docker build -t cb-backend:local apps/backend

# R4 (U1): static route, image served from the container, absolute og:image after deploy
env -i PATH="$PATH" HOME="$HOME" pnpm --filter @cb/web build | grep -E '○ /opengraph-image'
cid=$(docker run -d -p 18080:8080 -e SITE_URL=http://localhost:18080 cb-web:local); sleep 3
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://localhost:18080/opengraph-image   # 200 image/png
curl -s http://localhost:18080/ | grep -oE '<meta (property|name)="(og:image|twitter:card|twitter:image)"[^>]*>'   # all three
docker rm -f "$cid"
W=$(gh variable get WEB_URL)   # after U1 deploys
curl -s "$W/" | grep -oE '<meta (property|name)="(og:image|twitter:card|twitter:image)"[^>]*>'   # absolute https://cb-web-… URLs

# R3 (U2): every relative link and image in the README resolves, and there are 4 distinct screenshots
! ( grep -oE '\]\(([^)#]+)' README.md | sed 's/](//' | grep -v '^http' | while read -r p; do test -e "$p" || echo "MISSING $p"; done ) | grep MISSING
test "$(grep -oE 'docs/images/[a-z-]+\.png' README.md | sort -u | wc -l)" -eq 4
pnpm exec prettier --check README.md
```
- R1: this plan's Log has 13 checklist lines, all pass, dated after U1's deploy.
- R2: the Sprint 1 and 2 blocks of `TASKS.md` have no `[~]`; `CHANGELOG.md` has 0.1.0, 0.2.0 and 0.2.1; `_index.md`
  shows both earlier plans `done`.
- R5: `git branch -a` lists only `main` (and Dependabot branches until they close); `gh pr list` is empty;
  `gh repo view --json homepageUrl,repositoryTopics` is set.

## Rollback
- U1: revert the PR on `main`; the next deploy drops the image, and pages fall back to no `og:image`.
- U2: revert the PR; the README returns to the previous version.
- O1: revert the `Sprint 1–2 wrap up` commit.
- O4: branch deletions are recoverable from the merge commits (`git branch CBS-N <sha>` from `TASKS.md`); a Dependabot
  ignore is undone with `@dependabot unignore this major version`.

## Log
- 2026-10-22: planned (scope A, base `main`, user screenshots: user choices).
- 2026-10-23: audited (PASS-WITH-CHANGES): 5 fixes applied (screenshots copied in from outside the repo,
  README Prettier check, failing link/image checks, `twitter` card only, CBS-11 and no Author recorded) plus 3 NOTE
  tweaks (size not weight, planned dates kept, R2 check scoped). Status audited.
