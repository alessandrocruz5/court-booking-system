import Link from "next/link";
import { ApiError, getAvailability } from "@/lib/api/client";
import { type BookingParams, bookingHref, formatHour, formatPeso } from "@/lib/booking/params";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";

/** Shown while the backend answers (it may be cold-starting). */
export function AvailabilitySkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading times" className="grid gap-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-xl border-2 border-line bg-white p-4">
          <div className="h-5 w-40 animate-pulse rounded bg-line" />
          <div className="mt-4 flex flex-wrap gap-2">
            {[0, 1, 2, 3, 4].map((j) => (
              <div key={j} className="h-11 w-28 animate-pulse rounded-lg bg-line" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** A failed load: a friendly message and a retry link, never the error's detail. */
export function LoadError({ href }: { href: string }) {
  return (
    <div role="alert" className="rounded-xl border-2 border-clay bg-white p-4">
      <p className="m-0 font-bold">We couldn&apos;t load times. Try again.</p>
      <Link href={href} className="btn mt-3">
        Retry
      </Link>
    </div>
  );
}

/** One card per court with its free start times, fetched from the backend on every request. */
export async function AvailabilityGrid({
  params,
  date,
}: {
  params: BookingParams;
  /** The date in effect: the URL's, or today. */
  date: string;
}) {
  const { sport } = params;
  if (!sport) {
    return <p className="m-0 text-ink/70">Pick a sport to see free times.</p>;
  }

  let availability;
  try {
    availability = await getAvailability({
      date,
      sport,
      coverage: params.coverage,
      hours: params.hours,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return <LoadError href={bookingHref(params, { date })} />;
    }
    throw error;
  }

  const courts = availability.courts.filter((c) => c.starts.length > 0);
  if (courts.length === 0) {
    return (
      <div className="rounded-xl border-2 border-line bg-white p-4">
        <p className="m-0 font-bold">No free times on this day.</p>
        <p className="mt-1 mb-0 text-sm text-ink/70">
          Try another date, a shorter duration or a different sport.
        </p>
      </div>
    );
  }

  return (
    <ul className="m-0 grid list-none gap-3 p-0">
      {courts.map((court) => (
        <li key={court.code} className="rounded-xl border-2 border-line bg-white p-4">
          <h3 className="disp m-0 text-lg">{court.name}</h3>
          <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0">
            {court.starts.map((slot) => {
              const on = params.court === court.code && params.start === slot.hour;
              return (
                <li key={slot.hour}>
                  <Link
                    href={bookingHref(params, { date, court: court.code, start: slot.hour })}
                    prefetch={false}
                    aria-current={on ? "true" : undefined}
                    className={`inline-flex min-h-11 items-center rounded-lg border-2 px-3 text-sm font-bold no-underline ${FOCUS} ${
                      on
                        ? slot.peak
                          ? "border-clay bg-clay text-white"
                          : "border-court bg-court text-white"
                        : slot.peak
                          ? "border-clay text-clay hover:bg-clay/10"
                          : "border-line text-ink hover:bg-line"
                    }`}
                  >
                    {formatHour(slot.hour)} · {formatPeso(slot.price_centavos)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ul>
  );
}
