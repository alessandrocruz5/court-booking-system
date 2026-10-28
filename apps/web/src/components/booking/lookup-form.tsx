"use client";

import { useActionState } from "react";
import type { BookingStatus, BookingSummary } from "@/lib/api/schemas";
import { type LookupState, lookup } from "@/lib/booking/lookup";
import { formatHour, formatPeso } from "@/lib/booking/params";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";
const INPUT = `block min-h-11 w-full rounded-[10px] border-[1.5px] border-line bg-white px-3.5 py-3 text-base text-ink ${FOCUS}`;

const INITIAL: LookupState = { values: { reference: "", email: "" } };

const STATUS: Record<BookingStatus, { label: string; className: string }> = {
  confirmed: { label: "Confirmed", className: "bg-court-soft text-[#166534]" },
  pending: { label: "Awaiting payment", className: "bg-[#ffedd5] text-warn-ink" },
  expired: { label: "Expired", className: "bg-hair text-slate-5" },
  cancelled: { label: "Cancelled", className: "bg-[#fee2e2] text-[#991b1b]" },
  needs_refund: {
    label: "Refund due",
    className: "border border-warn-line bg-warn-bg text-warn-ink",
  },
};

/** The lookup form and, below it, the matching booking's summary. */
export function LookupForm() {
  const [state, formAction, pending] = useActionState(lookup, INITIAL);

  return (
    <div className="grid gap-3.5">
      <form
        action={formAction}
        className="grid gap-3.5 rounded-2xl border border-line-soft bg-white p-[22px]"
      >
        <div>
          <label htmlFor="reference" className="mb-1.5 block text-sm font-bold">
            Booking reference
          </label>
          <input
            id="reference"
            name="reference"
            type="text"
            required
            maxLength={20}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="KC-XXXXXX"
            aria-describedby="reference-hint"
            defaultValue={state.values.reference}
            className={`${INPUT} font-mono text-lg tracking-[0.06em] uppercase`}
          />
          <p id="reference-hint" className="m-0 mt-1.5 text-[13px] text-slate-5">
            References start with KC-.
          </p>
        </div>

        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-bold">
            Email used for the booking
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            maxLength={254}
            autoComplete="email"
            defaultValue={state.values.email}
            className={INPUT}
          />
        </div>

        <div>
          <button
            type="submit"
            disabled={pending}
            aria-disabled={pending}
            className="btn btn-accent w-full disabled:cursor-wait disabled:opacity-70 sm:w-auto"
          >
            {pending ? "Looking…" : "Find booking"}
          </button>
        </div>
      </form>

      {state.message ? (
        <p
          role="alert"
          className="m-0 rounded-xl border border-warn-line bg-warn-bg px-4 py-3.5 text-[15px] text-warn-ink"
        >
          {state.message}
        </p>
      ) : null}

      <div aria-live="polite">{state.booking ? <Summary booking={state.booking} /> : null}</div>
    </div>
  );
}

const SPORT_LABEL: Record<string, string> = {
  basketball: "Basketball",
  volleyball: "Volleyball",
  tennis: "Tennis",
  badminton: "Badminton",
  pickleball: "Pickleball",
};

/** `Sat 31 Oct`, from a local `YYYY-MM-DD`. */
function formatDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)));
}

function Summary({ booking }: { booking: BookingSummary }) {
  // A lapsed hold the nightly sweep hasn't reached yet is still stored as pending.
  const lapsed =
    booking.status === "pending" &&
    booking.hold_expires_at !== null &&
    new Date(booking.hold_expires_at).getTime() < Date.now();
  const status = STATUS[lapsed ? "expired" : booking.status];
  const sport = booking.sport ? (SPORT_LABEL[booking.sport] ?? booking.sport) : null;
  const coverage =
    booking.coverage === "half"
      ? `half court${booking.half ? ` (side ${booking.half})` : ""}`
      : "full court";
  const rows: [string, string][] = [
    ["Court", booking.court.name],
    ["Sport", sport ? `${sport}, ${coverage}` : coverage],
    ["Date", formatDate(booking.date)],
    [
      "Time",
      `${formatHour(booking.start_hour)}–${formatHour(booking.start_hour + booking.hours)} (${booking.hours} ${
        booking.hours === 1 ? "hour" : "hours"
      })`,
    ],
    ["Amount", formatPeso(booking.price_centavos)],
  ];

  return (
    <section
      aria-labelledby="booking-result"
      className="overflow-hidden rounded-2xl border-2 border-court bg-white"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 bg-court-tint px-[22px] py-[18px]">
        <h2
          id="booking-result"
          className="m-0 font-mono text-[22px] font-bold tracking-[0.04em] break-all"
        >
          <span className="sr-only">Booking </span>
          {booking.reference}
        </h2>
        <span className={`rounded-full px-2.5 py-1 text-[12.5px] font-bold ${status.className}`}>
          {status.label}
        </span>
      </div>
      <dl className="m-0">
        {rows.map(([term, value]) => (
          <div
            key={term}
            className="flex justify-between gap-4 border-t border-hair px-[22px] py-[13px] text-[15.5px]"
          >
            <dt className="text-slate-5">{term}</dt>
            <dd className="m-0 text-right font-bold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
