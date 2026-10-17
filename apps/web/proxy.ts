import { type NextRequest, NextResponse } from "next/server";
import { buildCsp } from "@/lib/csp";

/**
 * Gives every page request a fresh nonce and its Content-Security-Policy. The policy goes on the
 * request too, so Next finds the nonce and adds it to its own scripts. It never redirects,
 * rewrites or reads cookies.
 */
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce, {
    isDev: process.env.NODE_ENV === "development",
    // Cloud Run sets K_SERVICE; `next start` on localhost doesn't, and must stay on http.
    upgradeInsecure: Boolean(process.env.K_SERVICE),
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: `/api/*` answers JSON (its `no-store` is set in next.config.ts), and static
      // assets need no policy. The App Router's own prefetches skip it, as Next's CSP guide
      // recommends. The guide's `purpose: prefetch` entry is left out: that is a browser prefetch
      // of the full HTML, which the browser may reuse, so it keeps its policy.
      source: "/((?!api/|_next/static|_next/image|favicon.ico).*)",
      missing: [{ type: "header", key: "next-router-prefetch" }],
    },
  ],
};
