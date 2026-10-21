import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import { ApiError, releaseCheckout } from "@/lib/api/client";
import type { CheckoutRelease } from "@/lib/api/schemas";
import { releaseHold } from "@/lib/booking/actions";
import { CHECKOUT_COOKIE, isReference, pickCheckout } from "@/lib/booking/checkout-cookie";

export const metadata: Metadata = { title: "Checkout cancelled", robots: { index: false } };

/**
 * Where PayMongo sends the visitor who backs out. Releases the hold named by the httpOnly cookie;
 * the backend never cancels a paid booking. The only search param read is `ref`, and it only picks
 * which of this browser's own cookie entries to release (`pickCheckout`); a `ref` that isn't in the
 * cookie picks none of them.
 *
 * A speculative prefetch or prerender must not release on the visitor's behalf, so it renders a
 * "Release my hold" button instead: a plain POST form (works without JavaScript) whose action
 * releases the same hold and reloads this page.
 */
export default async function CancelledPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { ref: rawRef } = await searchParams;
  const ref = isReference(rawRef) ? rawRef : undefined;
  const query = ref ? `?ref=${encodeURIComponent(ref)}` : "";
  const checkoutSessionId = pickCheckout((await cookies()).get(CHECKOUT_COOKIE)?.value, ref);

  if (checkoutSessionId && isPrefetch(await headers())) {
    return (
      <Result eyebrow="Checkout cancelled" title="Release your hold?">
        <p className="mt-4 max-w-xl">Release the time you were holding so others can book it.</p>
        <form action={releaseHold} className="row">
          {ref ? <input type="hidden" name="ref" value={ref} /> : null}
          <button type="submit" className="btn btn-accent">
            Release my hold
          </button>
        </form>
      </Result>
    );
  }

  const status = await release(checkoutSessionId);

  switch (status) {
    case "released":
      return (
        <Result eyebrow="Checkout cancelled" title="No worries.">
          <p className="mt-4 max-w-xl">Your hold was released. No payment was taken.</p>
          <div className="row">
            <Link href="/book" className="btn btn-accent">
              Pick another time
            </Link>
          </div>
        </Result>
      );
    case "already_paid":
      return (
        <Result eyebrow="Already paid" title="You're all set.">
          <p className="mt-4 max-w-xl">This booking is already paid.</p>
          <div className="row">
            <Link href={`/book/success${query}`} prefetch={false} className="btn btn-accent">
              See your booking
            </Link>
          </div>
        </Result>
      );
    case "not_found":
      return (
        <Result eyebrow="Checkout cancelled" title="Nothing to release.">
          <p className="mt-4 max-w-xl">
            We couldn&apos;t find a hold to release. It may have already ended.
          </p>
          <div className="row">
            <Link href="/book" className="btn btn-accent">
              Book a court
            </Link>
          </div>
        </Result>
      );
    case "unavailable":
      return (
        <Result eyebrow="Try again" title="Still checking.">
          <p className="mt-4 max-w-xl">We couldn&apos;t check right now. Try again in a moment.</p>
          <div className="row">
            <Link href={`/book/cancelled${query}`} prefetch={false} className="btn btn-accent">
              Check again
            </Link>
            <Link href="/book" className="btn">
              Book a court
            </Link>
          </div>
        </Result>
      );
  }
}

/**
 * A browser's speculative load: `Sec-Purpose`/`Purpose: prefetch` (also `prefetch;prerender`).
 * Next's own router prefetch never reaches this page: `headers()` hides `next-router-prefetch`,
 * every link here is `prefetch={false}`, and a prefetch of `/book/*` stops at `book/loading.tsx`.
 */
function isPrefetch(requestHeaders: Headers): boolean {
  const purpose = `${requestHeaders.get("sec-purpose") ?? ""} ${requestHeaders.get("purpose") ?? ""}`;
  return purpose.toLowerCase().includes("prefetch");
}

async function release(
  checkoutSessionId: string | undefined,
): Promise<CheckoutRelease["status"] | "unavailable"> {
  // No cookie: there is no hold this browser could release, so the backend isn't called.
  if (!checkoutSessionId) return "released";
  try {
    return (await releaseCheckout(checkoutSessionId)).status;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    console.error(`checkout.release_failed ${error.code}`);
    return "unavailable";
  }
}

function Result({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <main className="wrap">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="disp text-4xl">{title}</h1>
      {children}
    </main>
  );
}
