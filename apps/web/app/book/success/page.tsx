import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import { ApiError, confirmCheckout } from "@/lib/api/client";
import type { BookingSummary, CheckoutStatus } from "@/lib/api/schemas";
import { CHECKOUT_COOKIE, isReference, pickCheckout } from "@/lib/booking/checkout-cookie";
import { formatHour, formatPeso } from "@/lib/booking/params";

export const metadata: Metadata = { title: "Your booking", robots: { index: false } };

/**
 * Where PayMongo sends the visitor after paying. The result comes only from the backend's check of
 * a session in the httpOnly cookie. The only search param read is `ref`, and it only picks which of
 * this browser's own cookie entries to check (`pickCheckout`); a `ref` that isn't in the cookie
 * picks none of them. Nothing in the URL can change what the backend says.
 */
export default async function SuccessPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { ref } = await searchParams;
  const checkoutSessionId = pickCheckout((await cookies()).get(CHECKOUT_COOKIE)?.value, ref);
  const href = isReference(ref) ? `/book/success?ref=${encodeURIComponent(ref)}` : "/book/success";
  const result = await check(checkoutSessionId);

  switch (result.status) {
    case "confirmed":
      return result.booking ? <Confirmed booking={result.booking} /> : <Unavailable href={href} />;
    case "pending":
      return (
        <Result eyebrow="Payment processing" title="Almost there.">
          <p className="mt-4 max-w-xl">Your payment is still processing.</p>
          <div className="row">
            <CheckAgain href={href} />
          </div>
        </Result>
      );
    case "needs_refund":
      return (
        <Result eyebrow="Refund due" title="Your booking didn't go through.">
          <p className="mt-4 max-w-xl">
            We received your payment, but this booking was cancelled or its slot was taken. Our
            staff will refund you (test mode).
          </p>
        </Result>
      );
    case "expired":
    case "cancelled":
      return (
        <Result eyebrow="Hold ended" title="Your hold has ended.">
          <p className="mt-4 max-w-xl">
            Your hold ended before we received payment. If you completed payment, it may still go
            through.
          </p>
          <div className="row">
            <CheckAgain href={href} />
            <Link href="/book" className="btn">
              Book a court
            </Link>
          </div>
        </Result>
      );
    case "not_found":
      return (
        <Result eyebrow="No booking here" title="Nothing to show yet.">
          <p className="mt-4 max-w-xl">We couldn&apos;t find a booking in this browser.</p>
          {/* GCash and Maya on mobile often return to a different browser than the one that paid. */}
          <p className="mt-2 max-w-xl">
            Paid in another app or browser? Your KC- reference was on the PayMongo checkout page.
            Use it with your email in Find your booking.
          </p>
          <div className="row">
            <Link href="/booking" className="btn btn-accent">
              Find your booking
            </Link>
          </div>
        </Result>
      );
    case "unavailable":
      return <Unavailable href={href} />;
  }
}

async function check(checkoutSessionId: string | undefined): Promise<CheckoutStatus> {
  // No cookie: nothing to look up, so the backend isn't called.
  if (!checkoutSessionId) return { status: "not_found", booking: null };
  try {
    return await confirmCheckout(checkoutSessionId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    console.error(`checkout.confirm_failed ${error.code}`);
    return { status: "unavailable", booking: null };
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

/** `href` is `/book/success`, with this page's `ref` when it is a valid reference. */
function CheckAgain({ href }: { href: string }) {
  return (
    <Link href={href} prefetch={false} className="btn btn-accent">
      Check again
    </Link>
  );
}

function Unavailable({ href }: { href: string }) {
  return (
    <Result eyebrow="Try again" title="Still checking.">
      <p className="mt-4 max-w-xl">We couldn&apos;t check right now. Try again in a moment.</p>
      <div className="row">
        <CheckAgain href={href} />
      </div>
    </Result>
  );
}

const SPORT_LABEL: Record<string, string> = {
  basketball: "Basketball",
  volleyball: "Volleyball",
  tennis: "Tennis",
  badminton: "Badminton",
  pickleball: "Pickleball",
};

const PAYMENT_METHOD_LABEL: Record<string, string> = {
  card: "Card",
  gcash: "GCash",
  grab_pay: "GrabPay",
  paymaya: "Maya",
  qrph: "QR Ph",
};

function Confirmed({ booking }: { booking: BookingSummary }) {
  const coverage =
    booking.coverage === "half"
      ? `Half court${booking.half ? ` (side ${booking.half})` : ""}`
      : "Full court";
  const rows: [string, string][] = [
    ["Court", booking.court.name],
    ["Sport", booking.sport ? (SPORT_LABEL[booking.sport] ?? booking.sport) : "—"],
    ["Coverage", coverage],
    ["Date", formatDate(booking.date)],
    ["Time", `${formatHour(booking.start_hour)}–${formatHour(booking.start_hour + booking.hours)}`],
    ["Amount paid", formatPeso(booking.price_centavos)],
  ];
  if (booking.payment_method) {
    rows.push([
      "Payment method",
      PAYMENT_METHOD_LABEL[booking.payment_method] ?? booking.payment_method,
    ]);
  }

  return (
    <Result eyebrow="Booking confirmed" title="You're booked.">
      <div className="mt-6 max-w-xl rounded-xl border-2 border-court bg-white p-4">
        <p className="m-0 text-sm font-bold text-ink/70">Your reference</p>
        <p className="disp m-0 mt-1 text-4xl break-all sm:text-5xl">{booking.reference}</p>
        <p className="mt-2 mb-0 font-bold">Show this reference at the front desk.</p>
        <dl className="m-0 mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="font-bold">{label}</dt>
              <dd className="m-0">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="row">
        <Link href="/booking" className="btn">
          Look up a booking
        </Link>
      </div>
    </Result>
  );
}

/** `Sat 31 Oct 2026`, from a local `YYYY-MM-DD`. */
function formatDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)));
}
