import Link from "next/link";
import { ApiError, getAvailabilityOnce } from "@/lib/api/client";
import type { Availability, Catalog } from "@/lib/api/schemas";
import { type BookingParams, bookingHref, formatHour, formatPeso } from "@/lib/booking/params";
import { CourtPicker } from "./court-picker";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";
const EMPTY_BOX =
  "rounded-xl border-[1.5px] border-dashed border-line p-7 text-center text-[15px] text-slate-5";

/** Shown while the backend answers (it may be cold-starting). */
export function AvailabilitySkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading times"
      className="grid grid-cols-[repeat(auto-fill,minmax(108px,1fr))] gap-2"
    >
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
        <div key={i} className="h-[76px] animate-pulse rounded-[10px] bg-hair" />
      ))}
    </div>
  );
}

/** A failed load: a friendly message and a retry link, never the error's detail. */
export function LoadError({ href }: { href: string }) {
  return (
    <div role="alert" className="rounded-xl border border-warn-line bg-warn-bg p-4 text-warn-ink">
      <p className="m-0 font-bold">We couldn&apos;t load times. Try again.</p>
      <Link href={href} className="btn mt-3">
        Retry
      </Link>
    </div>
  );
}

type Tile = {
  hour: number;
  /** How many courts are free at this hour. */
  free: number;
  /** The cheapest free slot at this hour, across courts. */
  cheapest?: Availability["courts"][number]["starts"][number];
  /** The court a click selects. */
  court?: string;
};

/** The current hour in Asia/Manila, 0 to 23. */
function manilaHour(now: Date = new Date()): number {
  return Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Manila",
      hour: "numeric",
      hourCycle: "h23",
    }).format(now),
  );
}

/**
 * The start times for the day, one tile per hour: the cheapest price across courts and how many
 * courts are free. An hour with no free court is a disabled "Booked" tile. With a start chosen, the
 * courts free at that hour follow as pills. Fetched from the backend on every request.
 */
export async function AvailabilityGrid({
  params,
  date,
  today,
  hours,
}: {
  params: BookingParams;
  /** The date in effect: the URL's, or today. */
  date: string;
  /** Today in Asia/Manila, `YYYY-MM-DD`. */
  today: string;
  /** The venue's opening hours, from the catalog. */
  hours: Catalog["hours"];
}) {
  const { sport } = params;
  if (!sport) {
    return <p className={`m-0 ${EMPTY_BOX}`}>Pick a sport to see free times.</p>;
  }

  let availability;
  try {
    // Deduped per request with the other steps' identical call; still fetched fresh each request.
    availability = await getAvailabilityOnce(date, sport, params.coverage, params.hours);
  } catch (error) {
    if (error instanceof ApiError) {
      return <LoadError href={bookingHref(params, { date })} />;
    }
    throw error;
  }

  // The API leaves out hours that have started, so today's tiles begin at the next hour.
  const isToday = date === today;
  const firstStart = isToday ? Math.max(hours.open, manilaHour() + 1) : hours.open;
  const lastStart = hours.close - params.hours;

  const tiles: Tile[] = [];
  for (let hour = firstStart; hour <= lastStart; hour++) {
    const free = availability.courts.flatMap((court) =>
      court.starts.filter((s) => s.hour === hour).map((slot) => ({ code: court.code, slot })),
    );
    const cheapest = free.reduce<(typeof free)[number] | undefined>(
      (best, entry) =>
        best === undefined || entry.slot.price_centavos < best.slot.price_centavos ? entry : best,
      undefined,
    );
    tiles.push({
      hour,
      free: free.length,
      cheapest: cheapest?.slot,
      // Keep the chosen court when it is free at this hour, otherwise the first free one.
      court: free.find((f) => f.code === params.court)?.code ?? free[0]?.code,
    });
  }
  const anyFree = tiles.some((t) => t.free > 0);

  const freeAtStart =
    params.start === undefined
      ? []
      : availability.courts
          .filter((court) => court.starts.some((s) => s.hour === params.start))
          .map(({ code, name }) => ({ code, name }));

  return (
    <>
      {isToday && tiles.length > 0 ? (
        <p className="m-0 -mt-1.5 mb-3 text-[13.5px] text-slate-5">
          Earlier times today have passed.
        </p>
      ) : null}
      {tiles.length > 0 ? (
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(108px,1fr))] gap-2 p-0">
          {tiles.map((tile) => {
            if (tile.free === 0 || !tile.cheapest || !tile.court) {
              return (
                <li key={tile.hour}>
                  <div
                    aria-disabled="true"
                    className="flex h-full cursor-not-allowed flex-col gap-0.5 rounded-[10px] border-[1.5px] border-line-soft bg-paper px-3 py-2.5 opacity-50"
                  >
                    <span className="text-base font-extrabold text-ink">
                      {formatHour(tile.hour)}
                    </span>
                    <span className="text-[13px] font-bold text-slate-4">Booked</span>
                    <span aria-hidden="true" className="text-[11.5px] text-slate-5">
                      —
                    </span>
                  </div>
                </li>
              );
            }
            const on = params.start === tile.hour;
            const lastCourt = tile.free === 1;
            return (
              <li key={tile.hour}>
                <Link
                  href={bookingHref(params, { date, court: tile.court, start: tile.hour })}
                  prefetch={false}
                  aria-current={on ? "true" : undefined}
                  className={`flex h-full flex-col gap-0.5 rounded-[10px] border-[1.5px] px-3 py-2.5 no-underline ${FOCUS} ${
                    on
                      ? "border-court bg-court text-white"
                      : "border-line-soft bg-white text-ink hover:border-court"
                  }`}
                >
                  <span className="text-base font-extrabold">{formatHour(tile.hour)}</span>
                  <span
                    className={`text-[13px] font-bold tabular-nums ${
                      on ? "text-white" : tile.cheapest.peak ? "text-clay" : "text-ink-3"
                    }`}
                  >
                    {formatPeso(tile.cheapest.price_centavos)}
                  </span>
                  <span
                    className={`text-[11.5px] ${
                      on ? "text-court-soft" : lastCourt ? "text-clay" : "text-slate-5"
                    }`}
                  >
                    {lastCourt ? "1 court left" : `${tile.free} free`}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
      {!anyFree ? (
        <p className={`m-0 ${tiles.length > 0 ? "mt-3" : ""} ${EMPTY_BOX}`}>
          No times left on this day. Try another day or a shorter length.
        </p>
      ) : null}
      {params.start !== undefined && freeAtStart.length > 0 ? (
        <CourtPicker params={params} date={date} hour={params.start} courts={freeAtStart} />
      ) : null}
    </>
  );
}
