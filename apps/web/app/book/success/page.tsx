import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import { CopyReference } from "@/components/booking/copy-reference";
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
          <Notice>
            <p className="m-0">Your payment is still processing.</p>
          </Notice>
          <div className="row">
            <CheckAgain href={href} />
          </div>
        </Result>
      );
    case "needs_refund":
      return (
        <Result eyebrow="Refund due" title="Your booking didn't go through.">
          <Notice>
            <p className="m-0">
              We received your payment, but this booking was cancelled or its slot was taken. Our
              staff will refund you (test mode).
            </p>
          </Notice>
        </Result>
      );
    case "expired":
    case "cancelled":
      return (
        <Result eyebrow="Hold ended" title="Your hold has ended.">
          <Notice>
            <p className="m-0">
              Your hold ended before we received payment. If you completed payment, it may still go
              through.
            </p>
          </Notice>
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
          <Notice>
            <p className="m-0">We couldn&apos;t find a booking in this browser.</p>
            {/* GCash and Maya on mobile often return to a different browser than the one that paid. */}
            <p className="m-0 mt-2">
              Paid in another app or browser? Your KC- reference was on the PayMongo checkout page.
              Use it with your email in Find your booking.
            </p>
          </Notice>
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

const H1 =
  "m-0 mb-6 text-[clamp(36px,6vw,52px)] leading-[1.05] font-black tracking-[-0.03em] font-stretch-[112%]";

/** The result shell: a 640px column with the eyebrow and heading. */
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
      <div className="mx-auto max-w-[640px]">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className={H1}>{title}</h1>
        {children}
      </div>
    </main>
  );
}

/** A warn-toned card for every state that isn't a confirmed booking. */
function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-warn-line bg-warn-bg px-[22px] py-[18px] text-base leading-normal text-warn-ink">
      {children}
    </div>
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
      <Notice>
        <p className="m-0">We couldn&apos;t check right now. Try again in a moment.</p>
      </Notice>
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
  const sport = booking.sport ? (SPORT_LABEL[booking.sport] ?? booking.sport) : null;
  const coverage =
    booking.coverage === "half"
      ? `half court${booking.half ? ` (side ${booking.half})` : ""}`
      : "full court";
  const rows: [string, string][] = [
    ["Court", booking.court.name],
    ["Sport", sport ? `${sport}, ${coverage}` : coverage.replace(/^f|^h/, (c) => c.toUpperCase())],
    ["Date", formatDate(booking.date)],
    [
      "Time",
      `${formatHour(booking.start_hour)} – ${formatHour(booking.start_hour + booking.hours)} (${
        booking.hours
      } ${booking.hours === 1 ? "hour" : "hours"})`,
    ],
    ["Amount paid", formatPeso(booking.price_centavos)],
  ];
  if (booking.payment_method) {
    rows.push([
      "Payment method",
      PAYMENT_METHOD_LABEL[booking.payment_method] ?? booking.payment_method,
    ]);
  }

  return (
    <main className="wrap">
      <div className="mx-auto max-w-[640px]">
        <div className="mb-2.5 flex items-center gap-3">
          <span
            aria-hidden="true"
            className="grid size-[34px] shrink-0 place-items-center rounded-full bg-court text-lg font-black text-white"
          >
            ✓
          </span>
          <p className="m-0 text-[12.5px] font-bold tracking-[0.14em] text-court-dark uppercase">
            Payment received
          </p>
        </div>
        <h1 className={H1}>You&apos;re booked.</h1>

        <section
          aria-labelledby="reference-label"
          className="rounded-[18px] bg-ink px-[26px] pt-[26px] pb-[22px] text-white"
        >
          <p
            id="reference-label"
            className="m-0 text-[13px] font-semibold tracking-[0.04em] text-slate-4"
          >
            Your reference
          </p>
          <div className="mt-1.5 mb-3.5 flex flex-wrap items-center justify-between gap-4">
            <p className="m-0 font-mono text-[clamp(34px,8vw,48px)] leading-tight font-bold tracking-[0.04em] break-all">
              {booking.reference}
            </p>
            <CopyReference reference={booking.reference} />
          </div>
          <p className="m-0 rounded-[10px] bg-court px-3.5 py-3 text-[15px] font-bold">
            Show this reference at the front desk when you arrive.
          </p>
        </section>

        <dl className="m-0 mt-3.5 rounded-2xl border border-line-soft bg-white">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex justify-between gap-4 border-t border-hair px-[22px] py-3.5 text-[15.5px] first:border-t-0"
            >
              <dt className="text-slate-5">{label}</dt>
              <dd className="m-0 text-right font-bold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>

        <div className="row">
          <Link href="/booking" className="btn">
            Look up a booking
          </Link>
          <Link href="/book" className="btn btn-accent">
            Book another court
          </Link>
        </div>
      </div>
    </main>
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
