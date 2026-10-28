import Link from "next/link";
import { type BookingParams, bookingHref, formatDayChip, isWeekend } from "@/lib/booking/params";

/**
 * The booking window as seven day buttons. Weekends are peak all day, so they carry a "Peak" mark
 * when the catalog says so. Rendered inside the "Day & length" card.
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
    <ul aria-label="Day" className="m-0 grid list-none grid-cols-7 gap-1.5 p-0">
      {dates.map((date) => {
        const on = date === selected;
        const peak = weekendsPeak && isWeekend(date);
        // `Today` or `Sat 18`: the first word is the top label, the day number is shown larger.
        const label = formatDayChip(date, today);
        return (
          <li key={date} className="min-w-0">
            <Link
              href={bookingHref(params, { date })}
              aria-current={on ? "date" : undefined}
              className={`flex min-h-11 flex-col items-center gap-px rounded-[10px] border-[1.5px] px-0.5 py-[9px] no-underline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court ${
                on
                  ? "border-ink bg-ink text-white"
                  : "border-line-soft bg-white text-ink hover:border-ink"
              }`}
            >
              <span className="text-[11px] font-semibold opacity-85 sm:text-xs">
                {label.split(" ")[0] ?? label}
              </span>
              <span className="text-xl leading-[1.1] font-extrabold font-stretch-[110%]">
                {Number(date.slice(8, 10))}
              </span>
              <span
                className={`h-3 text-[9.5px] font-extrabold tracking-[0.08em] uppercase ${on ? "text-warn-line" : "text-clay"}`}
              >
                {peak ? "Peak" : ""}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
