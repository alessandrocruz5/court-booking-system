# syntax=docker/dockerfile:1

# Next.js storefront for Cloud Run. Build context is the repo root:
#   docker build -f apps/web/Dockerfile -t cb-web:local .
# The build reads no environment: every variable is read per request at runtime.

FROM node:26-slim AS base
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

# A workspace subset holding only @cb/web and the packages it depends on.
FROM base AS pruner
COPY . .
# The exact turbo version the root importer locks in pnpm-lock.yaml, so every build (CI and deploy)
# runs the same release; the build fails if it can't be found.
# Telemetry opt-outs are set per command, never baked into the image.
RUN export TURBO_TELEMETRY_DISABLED=1 \
    && TURBO_VERSION="$(awk '/^      turbo:$/ { f = 1; next } f && /^        version:/ { print $2; exit }' pnpm-lock.yaml)" \
    && test -n "$TURBO_VERSION" \
    && pnpm dlx "turbo@${TURBO_VERSION}" prune @cb/web --docker

FROM base AS builder
# Manifests and lockfile first, so the install layer is reused until a dependency changes.
COPY --from=pruner /app/out/json/ ./
COPY --from=pruner /app/out/pnpm-lock.yaml ./pnpm-lock.yaml
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY --from=pruner /app/out/full/ ./
RUN TURBO_TELEMETRY_DISABLED=1 pnpm turbo run build --filter=@cb/web

FROM node:26-slim AS runner
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=8080
WORKDIR /app
# The standalone server traces its own node_modules; static assets and public/ are copied beside it.
COPY --from=builder --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /app/apps/web/public ./apps/web/public
USER node
EXPOSE 8080
CMD ["node", "apps/web/server.js"]
