"use client";

import Link from "next/link";

// Never render error.message or the stack: they can carry personal data. Only the digest, an
// opaque hash, is shown so it can be matched to server logs.
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main className="wrap">
      <p className="eyebrow">Something went wrong</p>
      <h1 className="disp text-4xl">We hit a snag.</h1>
      <p className="mt-4 max-w-xl">
        Nothing was charged. If you were paying, your payment is safe: open your booking again in a
        minute, or start over.
      </p>
      {error.digest ? <p className="mt-4 text-sm">Reference: {error.digest}</p> : null}
      <div className="row">
        <button type="button" className="btn btn-accent" onClick={() => retry()}>
          Try again
        </button>
        <Link href="/" className="btn">
          Back to the start
        </Link>
      </div>
    </main>
  );
}
