"use client";

import { useActionState } from "react";
import type { BookingStatus, BookingSummary } from "@/lib/api/schemas";
import { type LookupState, lookup } from "@/lib/booking/lookup";
import { formatHour, formatPeso } from "@/lib/booking/params";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";
const INPUT = `block min-h-11 w-full rounded-lg border-2 border-line bg-white px-3 text-base text-ink ${FOCUS}`;

const INITIAL: LookupState = { values: { reference: "", email: "" } };

const STATUS: Record<BookingStatus, { label: string; className: string }> = {
  confirmed: { label: "Confirmed", className: "bg-court text-white" },
  pending: { label: "Awaiting payment", className: "bg-ink text-paper" },
  expired: { label: "Expired", className: "bg-line text-ink" },
  cancelled: { label: "Cancelled", className: "bg-line text-ink" },
  needs_refund: { label: "Refund due", className: "bg-clay text-white" },
};

/** The lookup form and, below it, the matching booking's summary. */
export function LookupForm() {
  const [state, formAction, pending] = useActionState(lookup, INITIAL);

  return (
    <div className="grid gap-6">
      <form action={formAction} className="grid gap-5">
        {state.message ? (
          <p role="alert" className="m-0 rounded-lg border-2 border-clay p-3 font-bold">
            {state.message}
          </p>
        ) : null}

        <div>
          <label htmlFor="reference" className="mb-1 block text-sm font-bold">
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
            placeholder="KC-7Q4M2X"
            defaultValue={state.values.reference}
            className={`${INPUT} uppercase`}
          />
        </div>

        <div>
          <label htmlFor="email" className="mb-1 block text-sm font-bold">
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
  const status = STATUS[booking.status];
  const sport = booking.sport ? (SPORT_LABEL[booking.sport] ?? booking.sport) : null;
  const coverage =
    booking.coverage === "half"
      ? `half court${booking.half ? ` (side ${booking.half})` : ""}`
      : "full court";
  const rows: [string, string][] = [
    ["Reference", booking.reference],
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
      className="rounded-xl border-2 border-court bg-white p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="booking-result" className="disp m-0 text-xl">
          Your booking
        </h2>
        <span className={`rounded-full px-3 py-1 text-sm font-bold ${status.className}`}>
          {status.label}
        </span>
      </div>
      <dl className="m-0 mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {rows.map(([term, value]) => (
          <div key={term} className="contents">
            <dt className="font-bold">{term}</dt>
            <dd className="m-0">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
