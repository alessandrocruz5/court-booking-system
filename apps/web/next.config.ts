import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cloud Run runs the self-contained server in .next/standalone.
  output: "standalone",
  // The monorepo root, so the standalone server traces workspace packages (@cb/env).
  outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url)),
  poweredByHeader: false,
  // Workspace packages ship TypeScript source, not builds.
  transpilePackages: ["@cb/env"],
  // A header set here overrides the route's own: API responses are never shared-cached, and a
  // route that should be cacheable needs an explicit exception in this list.
  async headers() {
    return [
      { source: "/api/:path*", headers: [{ key: "Cache-Control", value: "no-store" }] },
      // Static security headers for every response. The CSP needs a per-request nonce, so it is
      // set in proxy.ts, not here.
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
