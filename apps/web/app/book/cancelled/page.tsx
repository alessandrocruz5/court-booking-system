import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import { ApiError, releaseCheckout } from "@/lib/api/client";
import type { CheckoutRelease } from "@/lib/api/schemas";

export const metadata: Metadata = { title: "Checkout cancelled", robots: { index: false } };

/** Set by `startCheckout` in `src/lib/booking/actions.ts` (which can't export it). */
const CHECKOUT_COOKIE = "cb_checkout";

/**
 * Where PayMongo sends the visitor who backs out. Releases the hold named by the httpOnly cookie;
 * the backend never cancels a paid booking. This page never reads `searchParams`.
 */
export default async function CancelledPage() {
  const checkoutSessionId = (await cookies()).get(CHECKOUT_COOKIE)?.value;
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
            <Link href="/book/success" prefetch={false} className="btn btn-accent">
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
            <Link href="/book/cancelled" prefetch={false} className="btn btn-accent">
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
