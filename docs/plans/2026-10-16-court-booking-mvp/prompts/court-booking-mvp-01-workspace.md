---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 01
unit: CBS-2
status: done
model: sonnet
effort: medium
depends_on: []
parallel_group: A
files:
  create:
    - package.json
    - pnpm-workspace.yaml
    - pnpm-lock.yaml
    - turbo.json
    - .nvmrc
    - .npmrc
    - .editorconfig
    - .gitignore
    - eslint.config.mjs
    - packages/config/package.json
    - packages/config/eslint.config.js
    - packages/config/prettier.config.js
    - packages/config/tsconfig/base.json
    - packages/env/package.json
    - packages/env/tsconfig.json
    - packages/env/eslint.config.js
    - packages/env/src/index.ts
    - packages/env/src/__tests__/create-env.test.ts
  modify: []
  delete: []
---
# 01 · Root workspace and shared TypeScript packages

## Task
Create the pnpm + Turborepo root of the court booking monorepo and its two shared TypeScript packages,
`@cb/config` and `@cb/env`. Copy them from the fun-run repo's proven setup, renaming the scope `@rr` → `@cb`.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. It's greenfield: only `README.md` and `LICENSE`
  exist, and `docs/plans/` holds planning notes (leave it alone).
- Reference repo, **read only, never modify**: `/Users/alessandrocruz/Code/fun-run-website`. Copy each file
  below, replacing every `@rr/` with `@cb/` and changing nothing else unless listed here:
  - `package.json` → root `package.json`. Set `"name": "court-booking-system"`. Keep
    `"packageManager": "pnpm@10.33.0"`, `"engines": {"node": ">=24"}` and `"prettier": "@cb/config/prettier"`.
    Keep the scripts `build`, `lint`, `typecheck` and `test` (all `turbo run …`), `format` and `format:check`. **Drop** the `e2e` script.
    Keep the devDependencies (`@cb/config: workspace:*`, eslint, prettier, turbo, typescript, vitest) at
    the same version ranges.
  - `pnpm-workspace.yaml` (`apps/*`, `packages/*`), `.nvmrc` (`24`), `.npmrc` (`engine-strict=true`),
    `eslint.config.mjs` (re-exports `@cb/config/eslint`), and `turbo.json` (same tasks: `build`, `lint`, `typecheck`, `test`).
  - `.editorconfig`: the same, plus a `[*.py]` section with `indent_size = 4`.
  - `.gitignore`: the same, minus the `# vercel` block and the playwright block, plus a `# python` block:
    `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`, `.ruff_cache/` and `apps/backend/staticfiles/`. Keep
    `.env*` with `!.env.example`, and keep `.claude`.
  - `packages/config/{package.json,eslint.config.js,prettier.config.js,tsconfig/base.json}`: as is, with the rename.
  - `packages/env/{package.json,tsconfig.json,eslint.config.js,src/index.ts,src/__tests__/create-env.test.ts}`:
    as is, with the rename. `createEnv(schema, source)` fails fast and lists every bad key without ever printing a value.
    Later prompts depend on that exact API.
- pnpm isn't on PATH on this machine. Run `corepack enable` first, or prefix commands with `corepack pnpm`.
  Then run `pnpm install` to generate `pnpm-lock.yaml`.
- Prettier formats `ts/tsx/js/mjs/cjs/json` only. Python formatting comes later, through ruff.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add apps (`apps/web` and `apps/backend` come in prompts 02–03), CI, Docker or docs.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test                     # @cb/env createEnv tests pass
! grep -rn '@rr/' --include='*.json' --include='*.js' --include='*.mjs' --include='*.ts' . --exclude-dir=node_modules
```
- `git status` shows only the files listed above. `docs/plans/` is unchanged.
