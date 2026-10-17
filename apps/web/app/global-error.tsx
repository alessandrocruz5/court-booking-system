"use client";

import "./globals.css";
import { TestModeBanner } from "@/components/test-mode-banner";

// Replaces the root layout, so it brings its own document and the test-mode banner. It is
// prerendered without a CSP nonce, so it must read fine with no JS: the exit link is a plain
// anchor. Never render error.message or the stack.
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <TestModeBanner />
        <main className="wrap">
          <p className="eyebrow">Something went wrong</p>
          <h1 className="disp text-4xl">We hit a snag.</h1>
          <p className="mt-4 max-w-xl">
            Nothing was charged. If you were paying, your payment is safe: open your booking again
            in a minute, or start over.
          </p>
          {error.digest ? <p className="mt-4 text-sm">Reference: {error.digest}</p> : null}
          <div className="row">
            <button type="button" className="btn btn-accent" onClick={() => retry()}>
              Try again
            </button>
            {/* A plain anchor, not next/link: it must work when the app itself is broken. */}
            <a href="/" className="btn">
              Back to the start
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
