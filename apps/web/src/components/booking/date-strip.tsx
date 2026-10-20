import Link from "next/link";
import { type BookingParams, bookingHref, formatDayChip, isWeekend } from "@/lib/booking/params";

/**
 * Step 3: the booking window as day chips. Weekends are peak all day, so they carry a "Peak" mark
 * when the catalog says so.
 */
export function DateStrip({
  params,
  dates,
  today,
  selected,
  weekendsPeak,
}: {
  params: BookingParams;
  dates: string[];
  today: string;
  /** The date in effect: the URL's, or today. */
  selected: string;
  weekendsPeak: boolean;
}) {
  return (
    <section aria-labelledby="date-heading">
      <h2 id="date-heading" className="disp text-xl">
        Date
      </h2>
      <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0">
        {dates.map((date) => {
          const on = date === selected;
          const peak = weekendsPeak && isWeekend(date);
          return (
            <li key={date}>
              <Link
                href={bookingHref(params, { date })}
                aria-current={on ? "date" : undefined}
                className={`inline-flex min-h-11 min-w-20 flex-col items-center justify-center rounded-lg border-2 px-3 py-1 text-sm font-bold no-underline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court ${
                  on ? "border-court bg-court text-white" : "border-line text-ink hover:bg-line"
                }`}
              >
                <span>{formatDayChip(date, today)}</span>
                {peak ? (
                  <span
                    className={`text-[0.7rem] font-bold uppercase tracking-wider ${on ? "text-white" : "text-clay"}`}
                  >
                    Peak
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
