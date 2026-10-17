import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import nextConfig from "../../../next.config";
import { config, proxy } from "../../../proxy";
import { buildCsp } from "../csp";

const NONCE = "bm9uY2UtZm9yLXRlc3Rz";

function directives(csp: string): Map<string, string[]> {
  return new Map(
    csp.split("; ").map((directive) => {
      const [name = "", ...values] = directive.split(" ");
      return [name, values];
    }),
  );
}

describe("buildCsp", () => {
  const prod = directives(buildCsp(NONCE, { isDev: false, upgradeInsecure: true }));
  const local = directives(buildCsp(NONCE, { isDev: false, upgradeInsecure: false }));
  const dev = directives(buildCsp(NONCE, { isDev: true, upgradeInsecure: false }));

  it("allows scripts by nonce, never inline", () => {
    const csp = buildCsp(NONCE, { isDev: false, upgradeInsecure: true });
    expect(csp.split(NONCE)).toHaveLength(2);
    expect(prod.get("script-src")).toContain(`'nonce-${NONCE}'`);
    expect(prod.get("script-src")).toContain("'strict-dynamic'");
    expect(prod.get("script-src")).not.toContain("'unsafe-inline'");
    expect(dev.get("script-src")).not.toContain("'unsafe-inline'");
  });

  it("allows eval only in development", () => {
    expect(prod.get("script-src")).not.toContain("'unsafe-eval'");
    expect(local.get("script-src")).not.toContain("'unsafe-eval'");
    expect(dev.get("script-src")).toContain("'unsafe-eval'");
  });

  it("allows no third-party origins", () => {
    for (const policy of [prod, local, dev]) {
      for (const [name, values] of policy) {
        expect(
          values.filter((value) => value.includes("://")),
          name,
        ).toEqual([]);
      }
      expect(policy.get("connect-src")).toEqual(["'self'"]);
      expect(policy.has("frame-src")).toBe(false);
    }
  });

  it("blocks plugins, framing and base-tag hijacks", () => {
    expect(prod.get("object-src")).toEqual(["'none'"]);
    expect(prod.get("frame-ancestors")).toEqual(["'none'"]);
    expect(prod.get("base-uri")).toEqual(["'self'"]);
    expect(prod.get("default-src")).toEqual(["'self'"]);
  });

  it("has no form-action, so the redirect to checkout.paymongo.com isn't blocked", () => {
    expect(prod.has("form-action")).toBe(false);
    expect(dev.has("form-action")).toBe(false);
  });

  it("upgrades insecure requests only when asked", () => {
    expect(prod.has("upgrade-insecure-requests")).toBe(true);
    expect(local.has("upgrade-insecure-requests")).toBe(false);
    expect(dev.has("upgrade-insecure-requests")).toBe(false);
  });
});

describe("next.config headers", () => {
  it("keeps no-store on /api/* and adds the security headers everywhere", async () => {
    const rules = (await nextConfig.headers?.()) ?? [];
    expect(rules).toContainEqual({
      source: "/api/:path*",
      headers: [{ key: "Cache-Control", value: "no-store" }],
    });

    const all = rules.find((rule) => rule.source === "/:path*");
    expect(all?.headers).toEqual([
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
      },
    ]);
    // The CSP needs a nonce per request (proxy.ts), and caching stays the API rule's business.
    const keys = rules.flatMap((rule) => rule.headers.map((header) => header.key.toLowerCase()));
    expect(keys).not.toContain("content-security-policy");
    expect(keys.filter((key) => key === "cache-control")).toHaveLength(1);
  });
});

describe("proxy", () => {
  function nonceOf(csp: string | null): string | undefined {
    return /'nonce-([^']+)'/.exec(csp ?? "")?.[1];
  }

  it("sends a CSP whose nonce matches the x-nonce header it forwards", () => {
    const response = proxy(new NextRequest("http://localhost:3000/"));
    expect(response.headers.get("x-middleware-next")).toBe("1");

    const csp = response.headers.get("content-security-policy");
    const forwardedNonce = response.headers.get("x-middleware-request-x-nonce");
    expect(forwardedNonce).toBeTruthy();
    expect(nonceOf(csp)).toBe(forwardedNonce);
    // Next reads the nonce from the request's copy of the policy.
    expect(response.headers.get("x-middleware-request-content-security-policy")).toBe(csp);
  });

  it("gives each request a new nonce", () => {
    const first = proxy(new NextRequest("http://localhost:3000/"));
    const second = proxy(new NextRequest("http://localhost:3000/"));
    expect(nonceOf(first.headers.get("content-security-policy"))).not.toBe(
      nonceOf(second.headers.get("content-security-policy")),
    );
  });

  it("matches pages but not the API or static assets", () => {
    const [entry] = config.matcher;
    const matcher = new RegExp(`^${entry?.source}$`);
    expect(matcher.test("/")).toBe(true);
    expect(matcher.test("/book")).toBe(true);
    expect(matcher.test("/booking/abc")).toBe(true);
    expect(matcher.test("/api")).toBe(true);
    expect(matcher.test("/apiary")).toBe(true);
    expect(matcher.test("/api/health")).toBe(false);
    expect(matcher.test("/api/anything/else")).toBe(false);
    expect(matcher.test("/_next/static/chunks/main.js")).toBe(false);
    expect(matcher.test("/favicon.ico")).toBe(false);
  });

  it("skips only the App Router's prefetches", () => {
    expect(config.matcher[0]?.missing).toEqual([{ type: "header", key: "next-router-prefetch" }]);
  });
});
