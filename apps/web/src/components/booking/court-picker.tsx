import Link from "next/link";
import { type BookingParams, bookingHref, formatHour } from "@/lib/booking/params";

/**
 * Pills for the courts free at the chosen start. With no court in the URL yet, the first pill shows
 * as selected. Every pill is a plain link, like the rest of the flow.
 */
export function CourtPicker({
  params,
  date,
  hour,
  courts,
}: {
  params: BookingParams;
  /** The date in effect: the URL's, or today. */
  date: string;
  /** The chosen start hour. */
  hour: number;
  /** The courts free at `hour`, in the API's order. */
  courts: { code: string; name: string }[];
}) {
  const active = params.court ?? courts[0]?.code;
  return (
    <div className="mt-[18px] border-t border-hair pt-4">
      <p id="court-label" className="m-0 mb-2.5 text-sm font-bold text-ink-3">
        Court{" "}
        <span className="font-medium text-slate-5">
          · {courts.length} free at {formatHour(hour)}
        </span>
      </p>
      <ul aria-labelledby="court-label" className="m-0 flex list-none flex-wrap gap-2 p-0">
        {courts.map((court) => {
          const on = court.code === active;
          return (
            <li key={court.code}>
              <Link
                href={bookingHref(params, { date, court: court.code, start: hour })}
                prefetch={false}
                aria-current={on ? "true" : undefined}
                className={`inline-flex min-h-11 items-center rounded-full border-[1.5px] px-4 py-[9px] text-[14.5px] font-bold no-underline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court ${
                  on
                    ? "border-ink bg-ink text-white"
                    : "border-line-soft bg-white text-ink hover:border-ink"
                }`}
              >
                {court.name}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
